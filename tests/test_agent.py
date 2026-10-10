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
        self.assertTrue(is_question("¿Cuántas facturas vencidas tiene Ferretería Ruiz?"))

    def test_is_question_palabra(self):
        self.assertTrue(is_question("cuántas facturas vencidas"))

    def test_is_not_question(self):
        self.assertFalse(is_question("Registra al cliente Papelería Los Andes"))

    def test_format_summary_con_respuesta(self):
        res = format_summary(
            "¿Cuántas facturas?",
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
        self.assertEqual(normalize_text("Papelería"), "papeleria")
        self.assertEqual(normalize_text("  Cartera "), "cartera")

    def test_find_element_exact(self):
        els = [Element("Archivo", 40, 50), Element("Cartera", 205, 50)]
        self.assertEqual(find_element(els, "Cartera").x, 205)

    def test_find_element_fuzzy(self):
        els = [Element("Papelería Los Andes", 100, 100)]
        self.assertEqual(find_element(els, "papeleria").x, 100)

    def test_find_element_none(self):
        self.assertIsNone(find_element([Element("A", 1, 1)], "zzz"))

    def test_box_center_normalizado(self):
        self.assertEqual(_box_center([0.14, 0.02, 0.18, 0.06], 1280, 800), (204, 32))

    def test_box_center_absoluto(self):
        self.assertEqual(_box_center([140, 48, 178, 70], 1280, 800), (159, 59))


class Scale1000Test(unittest.TestCase):
    """Verificado contra la pantalla real 1280x800 (spikes/captures/facturas.png)."""

    def test_scale_for(self):
        self.assertEqual(scale_for("qwen/qwen3-vl-235b-a22b-instruct"), 1000)
        self.assertEqual(scale_for("qwen/qwen3-vl-30b-a3b-instruct"), 1000)
        self.assertIsNone(scale_for("qwen/qwen2.5-vl-72b-instruct"))

    def test_buscar_0_1000(self):
        # Buscar real: centro (382,130). Qwen3-VL lo reportó centrado en (298,162) sobre 1000.
        self.assertEqual(_box_center([270, 150, 326, 174], 1280, 800, 1000), (381, 129))

    def test_anterior_y_bajo(self):
        # y=854/1000 no es un píxel imposible: son 683px.
        cx, cy = _box_center([20, 840, 54, 868], 1280, 800, 1000)
        self.assertEqual((cx, cy), (47, 683))

    def test_parse_item_formas(self):
        self.assertEqual(parse_item({"text": "A", "box": [1, 2, 3, 4]}), ("A", [1, 2, 3, 4]))
        self.assertEqual(parse_item(["Buscar", 270, 150, 326, 174]), ("Buscar", [270, 150, 326, 174]))
        self.assertEqual(parse_item("x"), ("", []))

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
        return (["Código", "Estado"], [[f"{prefix}{i}", "Vencida"] for i in range(n)])

    def test_is_count_question(self):
        from agent.summarize import is_count_question

        self.assertTrue(is_count_question("¿Cuántas facturas vencidas tiene Ferretería Ruiz?"))
        self.assertFalse(is_count_question("¿Cuánto cuesta la factura FV-1?"))

    async def test_tres_paginas(self):
        self._patch([self._page("A", 20), self._page("B", 20), self._page("C", 5)])
        frames = iter([object(), object()])

        async def nxt():
            return next(frames, None)

        self.assertEqual(await extract_answer("¿Cuántas facturas?", object(), next_page=nxt), "45")

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
        hs = parse_plan({"plan": [{"hito": "Abrir Facturas", "pantalla_esperada": "Título Facturas"}]})
        self.assertEqual(hs[0].text, "Abrir Facturas")
        self.assertEqual(hs[0].expected, "Título Facturas")

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
            Element("Clientes", 100, 50),
            Element("Cliente", 300, 200),
            Element("Buscar", 500, 200),
        ]

    def test_puntuacion_ignorada(self):
        self.assertEqual(normalize_text("Cliente:"), "cliente")
        self.assertEqual(normalize_text("Estado *"), "estado")

    def test_campo_no_se_confunde_con_menu(self):
        self.assertEqual(find_element(self.els, "Cliente:").x, 300)
        self.assertEqual(find_element(self.els, "Clientes").x, 100)

    def test_parcial_prefiere_longitud_cercana(self):
        els = [Element("Facturas pendientes de cobro", 1, 1), Element("Facturas", 2, 2)]
        self.assertEqual(find_element(els, "factura").x, 2)

    def test_resolve_por_indice(self):
        self.assertEqual(resolve_element(self.els, 2, "Cliente").x, 300)

    def test_resolve_indice_incoherente_manda_texto(self):
        self.assertEqual(resolve_element(self.els, 1, "Buscar").x, 500)

    def test_resolve_indice_invalido_usa_texto(self):
        self.assertEqual(resolve_element(self.els, 99, "Buscar").x, 500)
        self.assertIsNone(resolve_element(self.els, "x", ""))

    def test_sort_elements_orden_lectura(self):
        els = [Element("b", 200, 10), Element("c", 10, 100), Element("a", 10, 10)]
        self.assertEqual([e.text for e in sort_elements(els)], ["a", "b", "c"])

    def test_describe_actions(self):
        d = describe_actions([{"op": "click_text", "text": "Cartera"}, {"op": "wait", "ms": 800}])
        self.assertEqual(d, 'clic "Cartera"')


if __name__ == "__main__":
    unittest.main()
