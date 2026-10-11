"""Tests de Fase 4 (agent/): lógica pura (sin red ni VNC)."""

import unittest

from agent.act import describe_actions, sort_elements
from agent.actions import find_element, normalize_coords, normalize_key, normalize_text, resolve_element
from agent.plan import parse_plan
from agent.redact import redact_text
from agent.pager import find_next_control
from agent.summarize import extract_answer, format_summary, is_question, parse_answer
from vision.locate import Element, _box_center, parse_item, scale_for


class ActionsTest(unittest.TestCase):
    def test_normalize_key_alias(self):
        self.assertEqual(normalize_key("Enter"), "Return")
        self.assertEqual(normalize_key("enter"), "Return")
        self.assertEqual(normalize_key("esc"), "Escape")
        self.assertEqual(normalize_key("Escape"), "Escape")

    def test_normalize_key_passthrough(self):
        self.assertEqual(normalize_key("Tab"), "Tab")
        self.assertEqual(normalize_key("F5"), "F5")

    def test_normalize_coords(self):
        self.assertEqual(normalize_coords(0.5, 0.25, 1280, 800), (640, 200))

    def test_normalize_coords_absolutos(self):
        self.assertEqual(normalize_coords(129, 29, 1280, 800), (129, 29))
        self.assertEqual(normalize_coords(156, 47, 1280, 800), (156, 47))

    def test_normalize_coords_clamp(self):
        self.assertEqual(normalize_coords(1.5, -0.5, 1280, 800), (1279, 0))
        self.assertEqual(normalize_coords(99999, 99999, 1280, 800), (1279, 799))


class SummarizeTest(unittest.TestCase):
    def test_is_question_signo(self):
        self.assertTrue(is_question("¿Cuántas órdenes atrasadas tiene Acme?"))

    def test_is_question_palabra(self):
        self.assertTrue(is_question("cuántas órdenes atrasadas"))

    def test_is_not_question(self):
        self.assertFalse(is_question("Registra al cliente Café Central"))

    def test_format_summary_con_respuesta(self):
        res = format_summary(
            "¿Cuántas órdenes?",
            estado="terminada",
            answer="45",
            steps=4,
            cost_usd=0.001,
        )
        self.assertIn("respuesta: 45", res)

    def test_format_summary_redacta_password(self):
        res = format_summary(
            "Tarea",
            estado="fallida",
            reason="falló con s3cr3t-demo",
            secrets=["s3cr3t-demo"],
        )
        self.assertNotIn("s3cr3t-demo", res)
        self.assertIn("<REDACTED>", res)


class RedactTest(unittest.TestCase):
    def test_redact_secret(self):
        self.assertEqual(redact_text("pwd=s3cr3t-demo", ["s3cr3t-demo"]), "pwd=<REDACTED>")

    def test_redact_ignora_cortos(self):
        self.assertEqual(redact_text("abc", ["abc"]), "abc")


class LocateTest(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Café"), "cafe")
        self.assertEqual(normalize_text("  Menú B "), "menu b")

    def test_find_element_exact(self):
        els = [Element("Menú A", 40, 50), Element("Menú B", 205, 50)]
        self.assertEqual(find_element(els, "Menú B").x, 205)

    def test_find_element_fuzzy(self):
        els = [Element("Café Central", 100, 100)]
        self.assertEqual(find_element(els, "cafe").x, 100)

    def test_find_element_none(self):
        self.assertIsNone(find_element([Element("A", 1, 1)], "zzz"))

    def test_box_center_normalizado(self):
        self.assertEqual(_box_center([0.14, 0.02, 0.18, 0.06], 1280, 800), (204, 32))

    def test_box_center_absoluto(self):
        self.assertEqual(_box_center([140, 48, 178, 70], 1280, 800), (159, 59))


class Scale1000Test(unittest.TestCase):
    """Verificado contra la pantalla real 1280x800 (spikes/captures)."""

    def test_scale_for(self):
        self.assertEqual(scale_for("qwen/qwen3-vl-235b-a22b-instruct"), 1000)
        self.assertEqual(scale_for("qwen/qwen3-vl-30b-a3b-instruct"), 1000)
        self.assertIsNone(scale_for("qwen/qwen2.5-vl-72b-instruct"))

    def test_boton_0_1000(self):
        # Botón real: centro (382,130). Qwen3-VL lo reportó centrado en (298,162) sobre 1000.
        self.assertEqual(_box_center([270, 150, 326, 174], 1280, 800, 1000), (381, 129))

    def test_anterior_y_bajo(self):
        # y=854/1000 no es un píxel imposible: son 683px.
        cx, cy = _box_center([20, 840, 54, 868], 1280, 800, 1000)
        self.assertEqual((cx, cy), (47, 683))

    def test_parse_item_formas(self):
        self.assertEqual(parse_item({"text": "A", "box": [1, 2, 3, 4]}), ("A", [1, 2, 3, 4]))
        self.assertEqual(parse_item(["Aplicar", 270, 150, 326, 174]), ("Aplicar", [270, 150, 326, 174]))
        self.assertEqual(parse_item("x"), ("", []))

    def test_caja_pegada_al_borde_no_se_toma_como_fraccion(self):
        # x1=1 en escala 0-1000 son ~1 px, no 1*1280
        self.assertEqual(_box_center([1, 500, 41, 540], 1280, 800, 1000), (26, 416))

    def test_fraccion_pese_a_escala(self):
        self.assertEqual(_box_center([0.14, 0.02, 0.18, 0.06], 1280, 800, 1000), (204, 32))


class AnswerTest(unittest.TestCase):
    def test_parse_conteo(self):
        p = parse_answer({"tipo": "conteo", "filas": ["A", " B ", ""], "hay_mas_paginas": True})
        self.assertEqual(p["filas"], ["A", "B"])
        self.assertTrue(p["mas"])

    def test_parse_dato_null(self):
        self.assertIsNone(parse_answer({"tipo": "dato", "respuesta": None})["respuesta"])
        self.assertIsNone(parse_answer({"respuesta": "null"})["respuesta"])

    def test_parse_total_con_puntos(self):
        self.assertEqual(parse_answer({"tipo": "conteo", "total_visible": "1.234"})["total"], 1234)

    def test_find_next_control(self):
        els = [Element("Anterior", 1, 1), Element("Siguiente", 9, 9)]
        self.assertEqual(find_next_control(els).x, 9)
        self.assertIsNone(find_next_control([Element("Anterior", 1, 1)]))


class PaginatedCountTest(unittest.IsolatedAsyncioTestCase):
    """extract_answer con VLM/LLM simulados: transcribe páginas, filtra y cuenta en código."""

    def _patch(self, pages, ids=None):
        import agent.summarize as sm

        it = iter(pages)

        async def fake_table(task, frame):
            return next(it)

        async def fake_ids(task, cols, rows):
            return ids(rows) if callable(ids) else (ids or [r[0] for r in rows])

        orig = (sm._ask_table, sm._select_ids)
        sm._ask_table, sm._select_ids = fake_table, fake_ids
        self.addCleanup(lambda: setattr(sm, "_ask_table", orig[0]))
        self.addCleanup(lambda: setattr(sm, "_select_ids", orig[1]))

    @staticmethod
    def _page(prefix, n):
        return (["Código", "Estado"], [[f"{prefix}{i}", "Atrasada"] for i in range(n)])

    def test_is_count_question(self):
        from agent.summarize import is_count_question

        self.assertTrue(is_count_question("¿Cuántas órdenes atrasadas tiene Acme?"))
        self.assertFalse(is_count_question("¿Cuánto cuesta la orden OR-1?"))

    async def test_tres_paginas(self):
        self._patch([self._page("A", 20), self._page("B", 20), self._page("C", 5)])
        frames = iter([object(), object()])

        async def nxt():
            return next(frames, None)

        self.assertEqual(await extract_answer("¿Cuántas órdenes?", object(), next_page=nxt), "45")

    async def test_una_pagina_sin_control(self):
        self._patch([self._page("A", 3)])
        self.assertEqual(await extract_answer("¿Cuántas?", object(), next_page=None), "3")

    async def test_filtra_por_ids_del_modelo_y_cuenta_en_codigo(self):
        self._patch([self._page("A", 10)], ids=lambda rows: ["A1", "A2", "A2", "ZZ"])  # dup e inexistente
        self.assertEqual(await extract_answer("¿Cuántas?", object()), "2")

    async def test_pagina_repetida_se_deduplica(self):
        self._patch([self._page("A", 4), self._page("A", 4)])
        frames = iter([object()])

        async def nxt():
            return next(frames, None)

        self.assertEqual(await extract_answer("¿Cuántas?", object(), next_page=nxt), "4")

    async def test_sin_tabla_no_inventa(self):
        self._patch([([], [])])
        self.assertIsNone(await extract_answer("¿Cuántas?", object()))

    async def test_tiempo_agotado_no_cuenta_parcial(self):
        self._patch([self._page("A", 20), self._page("B", 20)])

        async def nxt():
            return object()

        self.assertIsNone(await extract_answer("¿Cuántas?", object(), next_page=nxt, can_continue=lambda: False))

    async def test_limite_de_paginas_no_cuenta_parcial(self):
        self._patch([self._page("A", 1), self._page("B", 1), self._page("C", 1)])

        async def nxt():
            return object()

        self.assertIsNone(await extract_answer("¿Cuántas?", object(), next_page=nxt, max_pages=2))

    async def test_dato_simple(self):
        import agent.summarize as sm

        async def fake(task, frame):
            return parse_answer({"tipo": "dato", "respuesta": "3157654321"})

        orig = sm._ask_answer
        sm._ask_answer = fake
        self.addCleanup(lambda: setattr(sm, "_ask_answer", orig))
        self.assertEqual(await extract_answer("¿Cuál es el teléfono de X?", object()), "3157654321")


class TypeIdempotentTest(unittest.IsolatedAsyncioTestCase):
    async def test_type_precede_select_all(self):
        import agent.actions as ac

        calls = []

        async def fake_click(c, x, y): calls.append(("click", x, y))
        async def fake_type(c, t): calls.append(("type", t))
        async def fake_sel(c): calls.append(("select_all",))
        orig = (ac.click, ac.type_text, ac.select_all)
        ac.click, ac.type_text, ac.select_all = fake_click, fake_type, fake_sel
        try:
            els = [Element("Cliente", 98, 131)]
            n = await ac.execute_actions(
                None,
                [{"op": "click_text", "index": 1, "text": "Cliente"}, {"op": "type", "text": "X"},
                 {"op": "select_all"}, {"op": "type", "text": "Y"}],
                1280, 800, elements=els,
            )
        finally:
            ac.click, ac.type_text, ac.select_all = orig
        self.assertEqual(n, 4)
        self.assertEqual(calls, [("click", 98, 131), ("select_all",), ("type", "X"), ("select_all",), ("type", "Y")])

    async def test_accion_invalida_no_tumba_el_lote(self):
        import agent.actions as ac

        calls = []

        async def fake_press(c, *k):
            if k[0] == "3072345193":
                raise KeyError(k[0])  # como asyncvnc con una tecla inexistente
            calls.append(k)

        orig = ac.press_key
        ac.press_key = fake_press
        try:
            n = await ac.execute_actions(
                None,
                [{"op": "press", "key": "3072345193"}, "basura", {"op": "press", "key": "Tab"}],
                1280, 800,
            )
        finally:
            ac.press_key = orig
        self.assertEqual(n, 1)
        self.assertEqual(calls, [("Tab",)])

    async def test_lote_largo_no_se_trunca(self):
        import agent.actions as ac

        n = await ac.execute_actions(None, [{"op": "wait", "ms": 0}] * 12, 1280, 800)
        self.assertEqual(n, 12)


class PlanParseTest(unittest.TestCase):
    def test_parse_plan_dict(self):
        hs = parse_plan({"plan": [{"hito": "Abrir Órdenes", "pantalla_esperada": "Título Órdenes"}]})
        self.assertEqual(hs[0].text, "Abrir Órdenes")
        self.assertEqual(hs[0].expected, "Título Órdenes")

    def test_parse_plan_strings_legacy(self):
        hs = parse_plan({"plan": ["a", "b"]})
        self.assertEqual([h.text for h in hs], ["a", "b"])
        self.assertEqual(hs[0].expected, "")

    def test_parse_plan_vacio(self):
        self.assertEqual(parse_plan(None), [])
        self.assertEqual(parse_plan({"plan": [{"hito": " "}]}), [])


class ElementResolveTest(unittest.TestCase):
    def setUp(self):
        self.els = [
            Element("Sujetos", 100, 50),
            Element("Cliente", 300, 200),
            Element("Aplicar", 500, 200),
        ]

    def test_puntuacion_ignorada(self):
        self.assertEqual(normalize_text("Cliente:"), "cliente")
        self.assertEqual(normalize_text("Estado *"), "estado")

    def test_campo_no_se_confunde_con_menu(self):
        self.assertEqual(find_element(self.els, "Cliente:").x, 300)
        self.assertEqual(find_element(self.els, "Sujetos").x, 100)

    def test_parcial_prefiere_longitud_cercana(self):
        els = [Element("Órdenes pendientes de cobro", 1, 1), Element("Órdenes", 2, 2)]
        self.assertEqual(find_element(els, "orden").x, 2)

    def test_resolve_por_indice(self):
        self.assertEqual(resolve_element(self.els, 2, "Cliente").x, 300)

    def test_resolve_indice_incoherente_manda_texto(self):
        self.assertEqual(resolve_element(self.els, 1, "Aplicar").x, 500)

    def test_resolve_indice_invalido_usa_texto(self):
        self.assertEqual(resolve_element(self.els, 99, "Aplicar").x, 500)
        self.assertIsNone(resolve_element(self.els, "x", ""))

    def test_sort_elements_orden_lectura(self):
        els = [Element("b", 200, 10), Element("c", 10, 100), Element("a", 10, 10)]
        self.assertEqual([e.text for e in sort_elements(els)], ["a", "b", "c"])

    def test_describe_actions(self):
        d = describe_actions([{"op": "click_text", "text": "Menú B"}, {"op": "wait", "ms": 800}])
        self.assertEqual(d, 'clic "Menú B"')


class DisambiguateTest(unittest.IsolatedAsyncioTestCase):
    COLS = ["Código", "Nombre", "Documento", "Ciudad"]

    def _patch(self, pages, ids):
        import agent.disambiguate as dis

        it = iter(pages)

        async def fake_table(task, frame, prompt_name="table"):
            return next(it)

        async def fake_ids(task, cols, rows):
            return ids(rows) if callable(ids) else ids

        orig = (dis._ask_table, dis._match_ids)
        dis._ask_table, dis._match_ids = fake_table, fake_ids
        self.addCleanup(lambda: setattr(dis, "_ask_table", orig[0]))
        self.addCleanup(lambda: setattr(dis, "_match_ids", orig[1]))

    def test_parse_plan_locate(self):
        hs = parse_plan({"plan": [{"hito": "a", "localiza_registro": "Ana"}, {"hito": "b", "localiza_registro": ""}, "c"]})
        self.assertEqual([h.locate for h in hs], ["Ana", "", ""])

    def test_find_prev_control(self):
        from agent.pager import find_prev_control

        self.assertEqual(find_prev_control([Element("Anterior", 5, 5), Element("Siguiente", 9, 9)]).x, 5)
        self.assertIsNone(find_prev_control([Element("Siguiente", 9, 9)]))

    async def test_dos_candidatos_es_ambiguo(self):
        from agent.disambiguate import ambiguity_reason, resolve_record

        rows = [["C1", "Ana Torres", "52345678", "X"], ["C2", "Ana Torres", "1019876543", "Y"]]
        self._patch([(self.COLS, rows)], ids=["C1", "C2"])
        res = await resolve_record("t", object())
        self.assertTrue(res.ambiguous)
        reason = ambiguity_reason("Ana Torres", res)
        self.assertIn("52345678", reason)
        self.assertIn("1019876543", reason)
        self.assertIn("No se modificó nada", reason)

    async def test_un_candidato_es_unico(self):
        from agent.disambiguate import resolve_record

        rows = [["C1", "Ana Torres", "1", "X"], ["C2", "Ana Torres Gómez", "2", "Y"]]
        self._patch([(self.COLS, rows)], ids=["C1"])
        res = await resolve_record("t", object())
        self.assertFalse(res.ambiguous)
        self.assertEqual(res.unique[0], "C1")

    async def test_ids_inventados_se_ignoran(self):
        from agent.disambiguate import resolve_record

        self._patch([(self.COLS, [["C1", "A", "1", "X"]])], ids=["C1", "ZZ"])
        res = await resolve_record("t", object())
        self.assertEqual([r[0] for r in res.candidates], ["C1"])

    async def test_homonimo_en_otra_pagina(self):
        from agent.disambiguate import resolve_record

        p1 = (self.COLS, [["C1", "A", "1", "X"]])
        p2 = (self.COLS, [["C2", "A", "2", "Y"]])
        self._patch([p1, p2], ids=lambda rows: [r[0] for r in rows])
        frames = iter([object()])

        async def nxt():
            return next(frames, None)

        res = await resolve_record("t", object(), next_page=nxt)
        self.assertTrue(res.ambiguous)
        self.assertEqual(res.pages, 2)

    async def test_sin_tabla_sin_candidatos(self):
        from agent.disambiguate import resolve_record

        self._patch([([], []), ([], [])], ids=[])
        res = await resolve_record("t", object())
        self.assertEqual(res.candidates, [])
        self.assertFalse(res.ambiguous)


class CostAccTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_suma_al_acumulador(self):
        import model.client as mc

        class R:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}

        class C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def post(self, *a, **k):
                return R()

        orig = mc.httpx.AsyncClient
        mc.httpx.AsyncClient = lambda **k: C()
        os_env = __import__("os").environ
        os_env.setdefault("OPENROUTER_API_KEY", "x-test-key")
        self.addCleanup(lambda: setattr(mc.httpx, "AsyncClient", orig))
        acc = []
        mc.cost_acc.set(acc)
        await mc.chat([{"role": "user", "content": "hi"}], "qwen/qwen3-vl-30b-a3b-instruct")
        await mc.chat([{"role": "user", "content": "hi"}], "qwen/qwen3-vl-30b-a3b-instruct")
        self.assertEqual(len(acc), 2)
        self.assertGreater(sum(acc), 0)


class GuardTest(unittest.TestCase):
    def test_is_commit_label(self):
        from agent.actions import is_commit_label

        for t in ("Guardar", "Crear cliente", "Exportar", "Save", "Guardar cambios"):
            self.assertTrue(is_commit_label(t), t)
        for t in ("Buscar", "Filtrar", "Nombre", "Cancelar", "Siguiente", "Cliente"):
            self.assertFalse(is_commit_label(t), t)

    def test_bloquea_mismo_boton_y_permite_con_error(self):
        from agent.act import ActState

        st = ActState()
        els = [Element("Guardar", 500, 600), Element("Nombre", 100, 100)]
        st.record([{"op": "click_text", "index": 1, "text": "Guardar"}], els)
        self.assertTrue(st.blocked(Element("Guardar", 505, 598)))
        self.assertFalse(st.blocked(Element("Guardar", 900, 100)))  # otro botón
        self.assertFalse(st.blocked(Element("Nombre", 100, 100)))
        self.assertFalse(st.blocked(Element("Guardar", 500, 600), "Error: el campo teléfono es obligatorio"))

    def test_no_registra_botones_de_busqueda(self):
        from agent.act import ActState

        st = ActState()
        st.record([{"op": "click_text", "index": 1, "text": "Buscar"}], [Element("Buscar", 1, 1)])
        self.assertEqual(st.committed, [])


class ScreenshotReconnectTest(unittest.IsolatedAsyncioTestCase):
    async def test_reconecta_una_vez_si_el_flujo_se_desincroniza(self):
        from desktop.capture import screenshot

        class C:
            calls = 0
            reconnected = 0

            async def screenshot(self):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError(3072345193)
                return "frame"

            async def _reconnect(self):
                self.reconnected += 1

        c = C()
        self.assertEqual(await screenshot(c), "frame")
        self.assertEqual(c.reconnected, 1)

    async def test_sin_reconexion_propaga(self):
        from desktop.capture import screenshot

        class C:
            async def screenshot(self):
                raise ValueError(1)

        with self.assertRaises(ValueError):
            await screenshot(C())


class PlanRejectTest(unittest.TestCase):
    def test_parse_rejection(self):
        from agent.plan import parse_rejection

        self.assertEqual(parse_rejection({"plan": [], "rechazo": "borrado masivo"}), "borrado masivo")
        self.assertEqual(parse_rejection({"plan": [], "rechazo": None}), "")
        self.assertEqual(parse_rejection({"rechazo": "null"}), "")
        self.assertEqual(parse_rejection(None), "")


class NotFoundTest(unittest.IsolatedAsyncioTestCase):
    async def test_sin_coincidencias_y_completo(self):
        import agent.disambiguate as dis

        async def fake_table(task, frame, prompt_name="table"):
            return (["Código", "Nombre"], [["C1", "Otro"]])

        async def fake_ids(task, cols, rows):
            return []

        orig = (dis._ask_table, dis._match_ids)
        dis._ask_table, dis._match_ids = fake_table, fake_ids
        self.addCleanup(lambda: setattr(dis, "_ask_table", orig[0]))
        self.addCleanup(lambda: setattr(dis, "_match_ids", orig[1]))
        res = await dis.resolve_record("t", object())
        self.assertEqual(res.candidates, [])
        self.assertTrue(res.complete)
        self.assertEqual(res.n_rows, 1)

    async def test_transcripcion_vacia_reintenta_una_vez(self):
        import agent.disambiguate as dis

        calls = []

        async def fake_table(task, frame, prompt_name="table"):
            calls.append(1)
            return ([], []) if len(calls) == 1 else (["Código"], [["C1"]])

        async def fake_ids(task, cols, rows):
            return ["C1"]

        orig = (dis._ask_table, dis._match_ids)
        dis._ask_table, dis._match_ids = fake_table, fake_ids
        self.addCleanup(lambda: setattr(dis, "_ask_table", orig[0]))
        self.addCleanup(lambda: setattr(dis, "_match_ids", orig[1]))
        res = await dis.resolve_record("t", object())
        self.assertEqual(len(calls), 2)
        self.assertEqual(res.unique[0], "C1")


class ChatTextFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_cae_al_respaldo_si_el_primario_falla(self):
        import model.client as mc

        calls = []

        async def fake_chat(messages, model, **kw):
            calls.append(model)
            if model.startswith("deepseek"):
                raise mc.LLMError("sin JSON", retryable=True)
            return mc.LLMResult("{}", {}, model, 1, 1, 0.0)

        orig = mc.chat
        mc.chat = fake_chat
        self.addCleanup(lambda: setattr(mc, "chat", orig))
        res = await mc.chat_text([], "deepseek/deepseek-v4-flash", json_mode=True)
        self.assertEqual(calls, ["deepseek/deepseek-v4-flash", mc.TEXT_FALLBACK])
        self.assertEqual(res.model, mc.TEXT_FALLBACK)


if __name__ == "__main__":
    unittest.main()
