"""Exploración manual: guarda capturas de todas las páginas de facturas de un cliente (sin Estado).

Uso: PYTHONPATH=src python spikes/dump_client_pages.py "Ferretería Ruiz" [estado]
"""
import asyncio, os, sys
import httpx
from PIL import Image
from desktop.capture import wait_and_capture
from desktop.connection import connect
from desktop.input import click, type_text, select_all, press_key
URL = "https://frontier-r1-tn06-production.up.railway.app"
OUT = os.path.join(os.path.dirname(__file__), "captures")
cliente = sys.argv[1]
estado = sys.argv[2] if len(sys.argv) > 2 else None

async def main():
    httpx.post(URL + "/__reset", headers={"Authorization": "Bearer " + os.environ["TOKEN_ESCRITORIO"]}, timeout=30)
    await asyncio.sleep(10)
    async with connect(URL, os.environ["CONTRASENA_ESCRITORIO"]) as c:
        await wait_and_capture(c); await asyncio.sleep(15)
        await click(c, 204, 48); await asyncio.sleep(1.2)
        await click(c, 211, 68); await asyncio.sleep(1.5)
        await click(c, 98, 131); await asyncio.sleep(0.4)
        await select_all(c); await type_text(c, cliente); await asyncio.sleep(0.5)
        if estado:
            await click(c, 260, 131); await asyncio.sleep(0.8)
            await type_text(c, estado); await press_key(c, "Return"); await asyncio.sleep(0.8)
        await click(c, 382, 130); await asyncio.sleep(1.5)
        for p in range(1, 12):
            f = await wait_and_capture(c)
            Image.fromarray(f[100:700, 0:1280]).save(os.path.join(OUT, f"pag{p}.png"))
            print("pagina", p, "guardada")
            before = f
            await click(c, 208, 684); await asyncio.sleep(1.5)
            after = await wait_and_capture(c)
            if (before != after).any(axis=2).mean() < 0.001:
                break
asyncio.run(main())
