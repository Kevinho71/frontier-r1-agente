"""Loop híbrido plan → act (batch) → check, con cortes (timeout, pasos, estancamiento)."""

from __future__ import annotations

import asyncio
import time

from desktop.connection import connect
from vision.diff import frame_signature
from vision.locate import detect_elements

from .act import ActState, act
from .check import check
from .pager import Pager
from .plan import plan
from .redact import redact_text
from .summarize import extract_answer, format_summary, is_question
from .trace import trace
from .types import Milestone, TaskResult

DEFAULT_TIMEOUT_S = 300
DEFAULT_RESERVE_S = 30
DEFAULT_MAX_STEPS = 40
MAX_ATTEMPTS_PER_MILESTONE = 7


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

    La compleción de cada hito la decide `check()` (verificación por visión),
    nunca el modelo de grounding. Cortes: timeout de 5 min (reservando ~30s para
    el resumen), max_steps, y estancamiento (3 pantallas iguales).
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
                hitos = [Milestone(task)]

            task_done = True
            reason = ""
            last_frame = None
            last_sig = None
            stall = 0
            history: list[str] = []
            act_state = ActState()
            prefetched = None
            det_task = None
            feedback = ""

            for hito in hitos:
                if remaining() <= 0:
                    reason = "tiempo agotado"
                    task_done = False
                    break

                hito_ok = False
                attempts = 0
                stall = 0
                feedback = ""
                trace("hito", text=hito.text, expected=hito.expected)
                while attempts < MAX_ATTEMPTS_PER_MILESTONE:
                    if remaining() <= 0:
                        reason = "tiempo agotado"
                        break
                    if steps >= max_steps:
                        reason = "límite de pasos alcanzado"
                        break

                    act_res = await act(
                        client,
                        task,
                        hito.text,
                        expected=hito.expected,
                        history=history,
                        feedback=feedback,
                        state=act_state,
                        prefetched=prefetched,
                    )
                    prefetched = None
                    cost += act_res.cost_usd
                    if act_res.description:
                        history.append(act_res.description)
                    steps += 1
                    last_frame = act_res.frame_after

                    sig = frame_signature(act_res.frame_after)
                    stall = stall + 1 if sig == last_sig else 0
                    last_sig = sig

                    if stall >= 3:
                        reason = "pantalla sin cambios"
                        break

                    if act_res.actions_executed == 0:
                        attempts += 1
                        continue

                    # La pantalla resultante también es la entrada del próximo act():
                    # se detecta en paralelo con el check (misma captura).
                    det_task = asyncio.create_task(detect_elements(act_res.frame_after))
                    prefetched = (act_res.frame_after, det_task)
                    chk = await check(client, task, hito.text, act_res.frame_after, hito.expected, frame=act_res.frame_after)
                    cost += chk.cost_usd
                    steps += 1
                    feedback = chk.description
                    if chk.ok:
                        hito_ok = True
                        break
                    attempts += 1

                if reason:
                    task_done = False
                    break
                if not hito_ok:
                    reason = f"no se pudo completar el hito: {hito.text}"
                    task_done = False
                    break

            # Para preguntas, solo se lee la respuesta si TODOS los hitos se verificaron:
            # una respuesta tomada de una pantalla equivocada es un falso éxito.
            answer = None
            if is_question(task) and task_done and last_frame is not None:
                pager = Pager(client, last_frame, det_task if prefetched and prefetched[0] is last_frame else None)
                try:
                    answer = await extract_answer(
                        task,
                        last_frame,
                        next_page=pager.next,
                        can_continue=lambda: (timeout_s - (time.monotonic() - t0)) > 12,  # el paginado puede usar la reserva
                    )
                except Exception as exc:
                    trace("answer.error", err=repr(exc))
                    answer = None
                cost += pager.cost
                if answer is None:
                    task_done = False
                    reason = "no se pudo determinar la respuesta en la pantalla"
                trace("answer", answer=answer)

            if det_task is not None and not det_task.done():
                det_task.cancel()
            estado = "terminada" if task_done else "fallida"
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
