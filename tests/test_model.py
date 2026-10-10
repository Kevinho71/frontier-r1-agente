"""Tests de Fase 3 (model/): router y helpers del cliente, sin red."""

import unittest

from model.client import _backoff, _estimate_cost, _extract_json
from model.registry import CANDIDATES, Capability
from model.router import is_exhausted, mark_exhausted, reset, select


class RouterTest(unittest.TestCase):
    def setUp(self):
        reset()

    def tearDown(self):
        reset()

    def test_select_primario(self):
        self.assertEqual(select(Capability.PLAN), "deepseek/deepseek-v4-flash")

    def test_check_usa_modelo_json(self):
        # ling-3.0-flash-vl devuelve vacío con json_object → CHECK debe usar qwen
        self.assertEqual(CANDIDATES[Capability.CHECK][0], "qwen/qwen3-vl-30b-a3b-instruct")
        self.assertNotIn("inclusionai/ling-3.0-flash-vl", CANDIDATES[Capability.CHECK])

    def test_ground_primario_qwen(self):
        # ui-tars devuelve coords en píxeles y apunta mal → qwen es el primario
        self.assertEqual(CANDIDATES[Capability.GROUND][0], "qwen/qwen3-vl-30b-a3b-instruct")

    def test_select_ground_fallback_al_exhausted(self):
        first = CANDIDATES[Capability.GROUND][0]
        mark_exhausted(first)
        self.assertEqual(select(Capability.GROUND), CANDIDATES[Capability.GROUND][1])

    def test_select_none_si_todos_agotados(self):
        for m in CANDIDATES[Capability.CHECK]:
            mark_exhausted(m)
        self.assertIsNone(select(Capability.CHECK))

    def test_mark_and_is_exhausted(self):
        self.assertFalse(is_exhausted("x"))
        mark_exhausted("x")
        self.assertTrue(is_exhausted("x"))

    def test_exclude(self):
        first = CANDIDATES[Capability.GROUND][0]
        self.assertEqual(select(Capability.GROUND, exclude={first}), CANDIDATES[Capability.GROUND][1])


class ClientHelpersTest(unittest.TestCase):
    def test_extract_json_puro(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_extract_json_con_texto_alrededor(self):
        txt = 'Aquí va: ```json\n{"ok": true, "n": 45}\n``` fin'
        self.assertEqual(_extract_json(txt), {"ok": True, "n": 45})

    def test_extract_json_none(self):
        self.assertIsNone(_extract_json("sin json aquí"))

    def test_estimate_cost(self):
        c = _estimate_cost("inclusionai/ling-3.0-flash-vl", 1000, 1000)
        self.assertAlmostEqual(c, 0.021 * 0.001 + 0.062 * 0.001, places=8)

    def test_estimate_cost_desconocido(self):
        self.assertEqual(_estimate_cost("modelo/x", 1_000_000, 0), 0.0)

    def test_backoff_creciente(self):
        self.assertLess(_backoff(0), _backoff(3))


if __name__ == "__main__":
    unittest.main()
