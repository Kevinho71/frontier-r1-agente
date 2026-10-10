"""Loop híbrido plan → act (batch) → check, con cortes (timeout, pasos, estancamiento)."""

from __future__ import annotations

import time

from desktop.connection import connect
from vision.diff import frame_signature

from .act import act
from .check import check
from .plan import plan
from .redact import redact_text
from .summarize import extract_answer, format_summary, is_question
from .types import TaskResult

DEFAULT_TIMEOUT_S = 300
DEFAULT_RESERVE_S = 30
DEFAULT_MAX_STEPS = 25
MAX_ATTEMPTS_PER_MILESTONE = 4


async def run_task(
    task: str,
    desktop_url: str,
    desktop_password: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_steps: int = DEFAULT_MAX_STEPS,
    reserve_s: int = DEFAULT_RESERVE_S,
) -> TaskResult:
    """Ejecuta una tarea sobre el escritorio remoto y devuelve estado + resumen.

    Cortes: timeout de 5 min (reservando ~30s para el resumen), max_steps, y
    estancamiento (3 pantallas iguales). Nunca deja la conexión VNC abierta.
    """
    secrets = [desktop_password]
    t0 = time.monotonic()
    steps = 0
    cost = 0.0

    def remaining() -> float:
        return timeout_s - reserve_s - (time.monotonic() - t0)

    try:
        async with connect(desktop_url, desktop_password) as client:
            hitos = await plan(client, task)
            if not hitos:
                hitos = [task]

            done = False
            reason = ""
            last_frame = None
            last_sig = None
            stall = 0

            for hito in hitos:
                if remaining() <= 0:
                    reason = "tiempo agotado"
                    break
                attempts = 0
                while attempts < MAX_ATTEMPTS_PER_MILESTONE:
                    if remaining() <= 0:
                        reason = "tiempo agotado"
                        break
                    if steps >= max_steps:
                        reason = "límite de pasos alcanzado"
                        break

                    act_res = await act(client, task, hito)
                    cost += act_res.cost_usd
                    steps += 1
                    last_frame = act_res.frame_after

                    sig = frame_signature(act_res.frame_after)
                    stall = stall + 1 if sig == last_sig else 0
                    last_sig = sig

                    if act_res.done:
                        done = True
                        break
                    if stall >= 3:
                        reason = "pantalla sin cambios"
                        break

                    chk = await check(client, task, hito, act_res.frame_after)
                    cost += chk.cost_usd
                    steps += 1
                    if chk.ok:
                        done = True
                        break
                    attempts += 1

                if done or reason:
                    break

            # Para preguntas, el "éxito" es extraer la respuesta, no un cambio de UI.
            answer = None
            if is_question(task) and last_frame is not None:
                try:
                    answer = await extract_answer(task, last_frame)
                except Exception:
                    answer = None
                if answer is not None:
                    done = True
                    reason = ""
                else:
                    done = False
                    if not reason:
                        reason = "no se pudo determinar la respuesta"

            estado = "terminada" if done else "fallida"
            resumen = format_summary(
                task,
                estado=estado,
                answer=answer,
                reason=reason,
                steps=steps,
                cost_usd=cost,
                secrets=secrets,
            )
            return TaskResult(estado, resumen, steps, cost)

    except Exception as exc:
        return TaskResult("fallida", redact_text(f"Error en la tarea: {exc}", secrets), steps, cost)
