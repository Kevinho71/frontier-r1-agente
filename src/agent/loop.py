"""Loop híbrido plan → act (batch) → check, con cortes (timeout, pasos, estancamiento)."""

from __future__ import annotations

import asyncio
import time

from desktop.connection import connect
from model import LLMError, cost_acc
from vision.diff import frame_signature
from vision.locate import detect_elements

from .act import ActState, act
from .check import check
from .disambiguate import ambiguity_reason, resolve_record, describe_row
from .pager import Pager
from .plan import plan
from .redact import redact_text
from .summarize import extract_answer, format_summary, is_question
from .trace import dump_frame, trace
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
    costs: list[float] = []
    cost_acc.set(costs)  # todas las llamadas a modelos de esta tarea suman aquí (OCR, plan, tablas...)
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
            carry_hint = ""

            for hito in hitos:
                if remaining() <= 0:
                    reason = "tiempo agotado"
                    task_done = False
                    break

                hito_ok = False
                attempts = 0
                stall = 0
                feedback = carry_hint
                carry_hint = ""
                trace("hito", text=hito.text, expected=hito.expected)
                while attempts < MAX_ATTEMPTS_PER_MILESTONE:
                    if remaining() <= 0:
                        reason = "tiempo agotado"
                        break
                    if steps >= max_steps:
                        reason = "límite de pasos alcanzado"
                        break

                    try:
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
                    except LLMError as exc:  # un fallo transitorio de modelo gasta un intento, no la tarea
                        trace("act.llm_error", err=repr(exc))
                        prefetched = None
                        attempts += 1
                        continue
                    prefetched = None
                    if act_res.description:
                        history.append(act_res.description)
                    steps += 1
                    last_frame = act_res.frame_after
                    dump_frame(act_res.frame_after, "act")

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
                    try:
                        chk = await check(client, task, hito.text, hito.expected, frame=act_res.frame_after)
                    except LLMError as exc:
                        trace("check.llm_error", err=repr(exc))
                        attempts += 1
                        continue
                    steps += 1
                    feedback = chk.description
                    if chk.ok:
                        hito_ok = True
                        if hito.locate:
                            pager = Pager(client, act_res.frame_after, det_task)
                            try:
                                res = await resolve_record(
                                    f"{task}\n(Registro a localizar: {hito.locate})",
                                    act_res.frame_after,
                                    next_page=pager.next,
                                    can_continue=lambda: remaining() > 45,
                                )
                            except Exception as exc:
                                trace("disambiguate.error", err=repr(exc))
                                res = None
                            if pager.moved:
                                await pager.back()
                                prefetched = None  # la pantalla pudo cambiar: act() captura de nuevo
                            if res is None:
                                # Sin poder comprobar que el registro es único no se toca nada.
                                reason = f'No se pudo verificar que "{hito.locate}" sea un único registro; no se modificó nada.'
                            elif res.ambiguous:
                                reason = ambiguity_reason(hito.locate, res)
                                trace("ambiguo", reason=reason)
                            elif res.candidates and not res.complete:
                                reason = (
                                    f'No se pudo recorrer todo el listado para confirmar que "{hito.locate}" sea único '
                                    "(demasiadas páginas o poco tiempo); no se modificó nada."
                                )
                            elif res is not None and res.unique:
                                carry_hint = (
                                    f"Registro objetivo ya identificado en el listado: {describe_row(res.cols, res.unique)}. "
                                    f"Ábrelo con el enlace o identificador '{res.unique[0]}' de su fila."
                                )
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
                if answer is None:
                    task_done = False
                    reason = "no se pudo determinar la respuesta en la pantalla"
                trace("answer", answer=answer)

            if det_task is not None and not det_task.done():
                det_task.cancel()
            cost = sum(costs)
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
        return TaskResult("fallida", redact_text(f"Error en la tarea: {exc}", secrets), steps, sum(costs))
