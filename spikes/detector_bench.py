"""Benchmark de detectores: latencia + boxes sobre capturas guardadas.

Uso: PYTHONPATH=src python spikes/detector_bench.py [captura.png ...]
Si no hay capturas, navega a Facturas en vivo y guarda spikes/captures/facturas.png.
"""
import asyncio, os, sys, time
import httpx
import numpy as np
from PIL import Image

from agent.actions import find_element
from desktop.capture import wait_and_capture
from desktop.connection import connect
from desktop.input import click, wait_ms
from vision.locate import detect_elements

URL = "https://frontier-r1-tn06-production.up.railway.app"
PWD = os.environ["CONTRASENA_ESCRITORIO"]
MODELS = sys.argv[1].split(",") if len(sys.argv) > 1 else [
    "qwen/qwen3-vl-235b-a22b-instruct", "qwen/qwen3-vl-30b-a3b-instruct", "qwen/qwen3-vl-8b-instruct"]
OUT = os.path.join(os.path.dirname(__file__), "captures", "facturas.png")


async def grab():
    httpx.post(URL + "/__reset", headers={"Authorization": "Bearer " + os.environ["TOKEN_ESCRITORIO"]}, timeout=30)
    await asyncio.sleep(10)  # el reset reinicia el navegador
    async with connect(URL, PWD) as c:
        await wait_and_capture(c)
        await asyncio.sleep(15)  # el escritorio ignora input los primeros segundos tras conectar
        await click(c, 204, 48)
        f = await wait_and_capture(c)
        els, _ = await detect_elements(f)
        print([(e.text, e.x, e.y) for e in els])
        fac = find_element(els, "Facturas")
        print("Facturas en", fac)
        await click(c, fac.x, fac.y)
        await wait_ms(800)
        f = await wait_and_capture(c)
        Image.fromarray(f).save(OUT)
        return f


async def main():
    if os.path.exists(OUT):
        frame = np.asarray(Image.open(OUT).convert("RGBA"))
    else:
        frame = await grab()
    truth = {"cartera": (204, 48), "cliente": (98, 131), "estado": (260, 131), "buscar": (382, 130),
             "limpiar": (466, 130), "exportar": (55, 166), "anterior": (52, 684), "siguiente": (208, 684)}
    for m in MODELS:
        t = time.monotonic()
        try:
            els, cost = await detect_elements(frame, m)
        except Exception as e:
            print(m, "ERROR", repr(e)[:200]); continue
        dt = time.monotonic() - t
        print(f"\n{m}: {dt:.1f}s ${cost:.5f} n={len(els)}")
        errs = []
        for k, (tx, ty) in truth.items():
            el = find_element(els, k)
            if el is None:
                print(f"    {k}: NO DETECTADO"); continue
            err = max(abs(el.x - tx), abs(el.y - ty))
            errs.append(err)
            print(f"    {k}: ({el.x},{el.y}) real ({tx},{ty}) err={err}px")
        print("    error max:", max(errs) if errs else None)
asyncio.run(main())
