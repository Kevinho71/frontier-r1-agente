"""Transcripción de tablas: compara modelos contra la verdad de terreno (pag1..4.png)."""
import asyncio, os, sys, time
import numpy as np
from PIL import Image
from model import chat_vision, load_prompt

TRUTH = {1: 12, 2: 13, 3: 15, 4: 5}   # filas con Cliente == "Ferretería Ruiz" y Estado == "Vencida"
ROWS = {1: 20, 2: 20, 3: 20, 4: 7}
MODELS = sys.argv[1].split(",")
DIR = os.path.join(os.path.dirname(__file__), "captures")

def norm(s): return " ".join(str(s).lower().split())

async def one(model, p):
    frame = np.asarray(Image.open(os.path.join(DIR, f"pag{p}.png")).convert("RGBA"))
    t = time.monotonic()
    res = await chat_vision(load_prompt("table"), frame, model, downscale_to=None, json_mode=True, max_tokens=2500)
    d = res.parsed or {}
    cols = [norm(c) for c in d.get("columnas", [])]
    rows = d.get("filas", [])
    try:
        ic, ie = cols.index("cliente"), cols.index("estado")
        n = sum(1 for r in rows if len(r) > max(ic, ie) and norm(r[ic]) == "ferretería ruiz" and norm(r[ie]) == "vencida")
    except ValueError:
        n = -1
    return p, len(rows), n, round(time.monotonic() - t, 1)

async def main():
    for m in MODELS:
        rs = await asyncio.gather(*[one(m, p) for p in TRUTH])
        ok = sum(n == TRUTH[p] for p, _, n, _ in rs)
        print(m, "| (pág, filas leídas, vencidas exactas, s):", rs, "| total", sum(max(n,0) for _, _, n, _ in rs), "(esp. 45) | filas ok:", sum(r == ROWS[p] for p, r, _, _ in rs), "/4 | pág ok:", ok, "/4")
asyncio.run(main())
