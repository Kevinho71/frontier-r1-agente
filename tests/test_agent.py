"""Tests de Fase 4 (agent/): lógica pura (sin red ni VNC)."""

import unittest

from agent.actions import normalize_coords, normalize_key
from agent.redact import redact_text
from agent.summarize import format_summary, is_question


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
            reason="falló con 0e6cf456",
            secrets=["0e6cf456"],
        )
        self.assertNotIn("0e6cf456", res)
        self.assertIn("<REDACTED>", res)


class RedactTest(unittest.TestCase):
    def test_redact_secret(self):
        self.assertEqual(redact_text("pwd=0e6cf456", ["0e6cf456"]), "pwd=<REDACTED>")

    def test_redact_ignora_cortos(self):
        self.assertEqual(redact_text("abc", ["abc"]), "abc")


if __name__ == "__main__":
    unittest.main()
