"""Servicio HTTP: encola tareas y las ejecuta en segundo plano (una conexión VNC por tarea)."""

from __future__ import annotations

import asyncio
import hmac
import os
import uuid
from collections import OrderedDict

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent.loop import run_task
from agent.redact import redact_text
from agent.trace import sink
from logs import TaskLog

TASK_TIMEOUT_S = 280  # el evaluador corta a los 300 s: el estado final debe quedar escrito antes
HARD_CAP_S = 292
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "4"))
MAX_STORED = 500


class Desktop(BaseModel):
    url: str
    password: str


class TaskRequest(BaseModel):
    tarea: str
    escritorio: Desktop


def create_app(runner=run_task, log_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Agente de escritorio remoto")
    tasks: OrderedDict[str, dict] = OrderedDict()
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    bg: set = set()
    data_dir = log_dir or os.environ.get("DATA_DIR", "/tmp/reto1-data")

    def auth(authorization: str | None = Header(default=None)):
        expected = os.environ.get("TEAM_TOKEN", "")
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not expected or not hmac.compare_digest(given, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def execute(task_id: str, req: TaskRequest):
        secrets = [req.escritorio.password]
        log = TaskLog(task_id, data_dir, secrets)
        rec = tasks[task_id]
        async with sem:
            sink.set(log.write)
            log.write("start", tarea=req.tarea)
            try:
                res = await asyncio.wait_for(
                    runner(req.tarea, req.escritorio.url, req.escritorio.password, timeout_s=TASK_TIMEOUT_S),
                    timeout=HARD_CAP_S,
                )
                rec.update(estado=res.estado, resumen=redact_text(res.resumen, secrets))
            except asyncio.TimeoutError:
                rec.update(estado="fallida", resumen="Tarea: tiempo agotado (5 min); se detuvo el trabajo.")
            except Exception as exc:  # nunca dejar la tarea en 'en_curso' para siempre
                rec.update(estado="fallida", resumen=redact_text(f"Error en la tarea: {exc}", secrets))
            log.write("end", estado=rec["estado"], resumen=rec["resumen"])

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/tasks", status_code=202, dependencies=[Depends(auth)])
    async def create_task(req: TaskRequest):
        task_id = uuid.uuid4().hex
        tasks[task_id] = {"estado": "en_curso", "resumen": ""}
        while len(tasks) > MAX_STORED:
            tasks.popitem(last=False)
        t = asyncio.create_task(execute(task_id, req))
        bg.add(t)
        t.add_done_callback(bg.discard)
        return {"task_id": task_id}

    @app.get("/tasks/{task_id}", dependencies=[Depends(auth)])
    async def get_task(task_id: str):
        rec = tasks.get(task_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="task not found")
        return {"estado": rec["estado"], "resumen": rec["resumen"]}

    return app


app = create_app()
