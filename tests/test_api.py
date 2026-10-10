"""Tests del servicio HTTP (sin red ni escritorio: el runner es un doble)."""

import asyncio
import os
import tempfile
import unittest

import httpx

from agent.types import TaskResult
from api.main import create_app

BODY = {"tarea": "haz algo", "escritorio": {"url": "wss://x/websockify", "password": "pw-secreta-123"}}
AUTH = {"Authorization": "Bearer tok-equipo"}


class ApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ["TEAM_TOKEN"] = "tok-equipo"
        self.tmp = tempfile.mkdtemp()

    def client(self, runner):
        app = create_app(runner=runner, log_dir=self.tmp)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    async def _poll(self, c, tid):
        for _ in range(100):
            r = await c.get(f"/tasks/{tid}", headers=AUTH)
            if r.json()["estado"] != "en_curso":
                return r.json()
            await asyncio.sleep(0.01)
        self.fail("no terminó")

    async def test_health(self):
        async with self.client(None) as c:
            self.assertEqual((await c.get("/health")).status_code, 200)

    async def test_auth(self):
        async with self.client(None) as c:
            self.assertEqual((await c.post("/tasks", json=BODY)).status_code, 401)
            self.assertEqual((await c.post("/tasks", json=BODY, headers={"Authorization": "Bearer mal"})).status_code, 401)
            self.assertEqual((await c.get("/tasks/x", headers={"Authorization": "Bearer mal"})).status_code, 401)

    async def test_flujo_y_redaccion(self):
        async def runner(task, url, pwd, **kw):
            await asyncio.sleep(0.05)
            return TaskResult("terminada", f"hecho con clave {pwd}", 3, 0.01)

        async with self.client(runner) as c:
            r = await c.post("/tasks", json=BODY, headers=AUTH)
            self.assertEqual(r.status_code, 202)
            tid = r.json()["task_id"]
            self.assertEqual((await c.get(f"/tasks/{tid}", headers=AUTH)).json()["estado"], "en_curso")
            out = await self._poll(c, tid)
            self.assertEqual(out["estado"], "terminada")
            self.assertNotIn("pw-secreta-123", out["resumen"])

    async def test_error_del_runner_es_fallida(self):
        async def runner(*a, **kw):
            raise RuntimeError("boom pw-secreta-123")

        async with self.client(runner) as c:
            tid = (await c.post("/tasks", json=BODY, headers=AUTH)).json()["task_id"]
            out = await self._poll(c, tid)
            self.assertEqual(out["estado"], "fallida")
            self.assertNotIn("pw-secreta-123", out["resumen"])

    async def test_404_y_body_invalido(self):
        async with self.client(None) as c:
            self.assertEqual((await c.get("/tasks/nope", headers=AUTH)).status_code, 404)
            self.assertEqual((await c.post("/tasks", json={"tarea": "x"}, headers=AUTH)).status_code, 422)

    async def test_log_jsonl_redactado(self):
        async def runner(*a, **kw):
            from agent.trace import trace

            trace("paso", clave="pw-secreta-123")
            return TaskResult("terminada", "ok", 1, 0.0)

        async with self.client(runner) as c:
            tid = (await c.post("/tasks", json=BODY, headers=AUTH)).json()["task_id"]
            await self._poll(c, tid)
        path = os.path.join(self.tmp, "tasks", f"{tid}.jsonl")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('"event": "paso"', text)
        self.assertNotIn("pw-secreta-123", text)


if __name__ == "__main__":
    unittest.main()
