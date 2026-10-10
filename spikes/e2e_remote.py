"""Prueba de punta a punta contra el servicio DESPLEGADO (contrato HTTP real).

Uso:
    BASE_URL=https://... TEAM_TOKEN=... source .env
    PYTHONPATH=src python spikes/e2e_remote.py E1 E2 E3 E4 E5 --reps 3

Por cada corrida: /__reset del escritorio, POST /tasks, polling cada 5 s (como el evaluador),
y al final /__check del escritorio + comparación del estado/respuesta esperados.
Las corridas son secuenciales (un solo escritorio). Resumen al final con la tasa de éxito.
"""

import argparse
import glob
import json
import os
import re
import sys
import time

import httpx

DESK = "https://frontier-r1-tn06-production.up.railway.app"
PRUEBAS = os.path.join(os.path.dirname(__file__), "..", "frontier-reto-1", "pruebas")


def load(tid):
    path = glob.glob(os.path.join(PRUEBAS, f"{tid}-*.json"))[0]
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def first_number(text):
    m = re.search(r"-?\d[\d.,]*", text or "")
    return m.group(0) if m else None


def run_one(base, team, pwd, dtoken, test):
    h = {"Authorization": f"Bearer {team}"}
    httpx.post(DESK + "/__reset", headers={"Authorization": f"Bearer {dtoken}"}, timeout=60)
    t0 = time.time()
    r = httpx.post(
        base + "/tasks",
        headers=h,
        json={"tarea": test["instruccion"], "escritorio": {"url": DESK.replace("https", "wss") + "/websockify", "password": pwd}},
        timeout=10,
    )
    post_s = time.time() - t0
    tid = r.json()["task_id"]
    out = {"estado": "en_curso", "resumen": ""}
    while time.time() - t0 < 330:
        time.sleep(5)
        out = httpx.get(f"{base}/tasks/{tid}", headers=h, timeout=15).json()
        if out["estado"] != "en_curso":
            break
    elapsed = time.time() - t0
    chk = httpx.post(DESK + "/__check", headers={"Authorization": f"Bearer {dtoken}"}, json=test, timeout=60).json()
    resumen = out["resumen"]
    problems = []
    if out["estado"] != test["estado_esperado"]:
        problems.append(f"estado {out['estado']} != {test['estado_esperado']}")
    if not chk.get("pass"):
        problems.append("/__check falló: " + ",".join(c["nombre"] for c in chk.get("checks", []) if not c["ok"]))
    if "respuesta_esperada" in test:
        line = next((l for l in resumen.splitlines() if l.lower().startswith("respuesta:")), "")
        if first_number(line) != str(test["respuesta_esperada"]):
            problems.append(f"respuesta {line!r} != {test['respuesta_esperada']}")
    for k in test.get("claves_razon", []):
        if k not in resumen:
            problems.append(f"falta clave {k} en el resumen")
    if pwd in resumen:
        problems.append("EL RESUMEN FILTRA LA CONTRASEÑA")
    if test["estado_esperado"] == "fallida" and "respuesta:" in resumen.lower() and "respuesta_esperada" not in test:
        problems.append("línea respuesta: inesperada")
    return {"id": test["id"], "ok": not problems, "problems": problems, "estado": out["estado"], "s": round(elapsed), "post_s": round(post_s, 2), "resumen": resumen}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    base = os.environ["BASE_URL"].rstrip("/")
    team, pwd, dtoken = os.environ["TEAM_TOKEN"], os.environ["CONTRASENA_ESCRITORIO"], os.environ["TOKEN_ESCRITORIO"]
    results = []
    for rep in range(1, a.reps + 1):
        for tid in a.ids:
            res = run_one(base, team, pwd, dtoken, load(tid))
            results.append(res)
            print(f"[{rep}] {res['id']} {'OK ' if res['ok'] else 'FAIL'} estado={res['estado']} {res['s']}s post={res['post_s']}s {res['problems']}", flush=True)
            if not res["ok"]:
                print("    resumen:", res["resumen"][:500].replace("\n", " | "), flush=True)
    print("\n== RESUMEN ==")
    for tid in a.ids:
        rs = [r for r in results if r["id"] == tid]
        print(f"{tid}: {sum(r['ok'] for r in rs)}/{len(rs)}  tiempos={[r['s'] for r in rs]}")
    httpx.post(DESK + "/__reset", headers={"Authorization": f"Bearer {dtoken}"}, timeout=60)


if __name__ == "__main__":
    main()
