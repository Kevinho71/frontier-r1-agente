"""Prueba en vivo del agente contra el escritorio de pruebas.

Uso:
    PYTHONPATH=src python spikes/live_agent_test.py "<tarea>" [--reset]

Hace POST /__reset (opcional), corre run_task y reporta estado/resumen.
Requiere OPENROUTER_API_KEY, CONTRASENA_ESCRITORIO y TOKEN_ESCRITORIO en el entorno.
"""

import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.loop import run_task  # noqa: E402

URL = "https://frontier-r1-tn06-production.up.railway.app"
PWD = os.environ["CONTRASENA_ESCRITORIO"]
RESET_TOKEN = os.environ.get("TOKEN_ESCRITORIO", "")


def reset_desktop():
    if not RESET_TOKEN:
        return
    r = httpx.post(
        URL + "/__reset",
        headers={"Authorization": f"Bearer {RESET_TOKEN}"},
        timeout=30,
    )
    print("[reset]", r.status_code, r.text[:120])


async def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "¿Cuántas facturas vencidas tiene Ferretería Ruiz?"
    if "--reset" in sys.argv:
        reset_desktop()
    result = await run_task(task, URL, PWD, timeout_s=180, max_steps=20, reserve_s=30)
    print("=== RESULT ===")
    print(result.to_dict())


if __name__ == "__main__":
    asyncio.run(main())
