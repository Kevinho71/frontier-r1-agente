"""Planificación inicial: OCR barato + modelo de texto → hitos."""

from __future__ import annotations

from desktop.capture import wait_and_capture
from model import Capability, chat, load_prompt, select
from vision.ocr import extract_text

from .trace import trace
from .types import Milestone


class TaskRejected(Exception):
    """El plan decidió que la tarea es imposible, contradictoria o peligrosa: no se toca nada."""


def parse_rejection(parsed) -> str:
    r = (parsed or {}).get("rechazo") if isinstance(parsed, dict) else None
    r = str(r).strip() if r else ""
    return "" if r.lower() in ("null", "none", "false") else r


def parse_plan(parsed) -> list[Milestone]:
    """Convierte la respuesta del modelo en hitos. Acepta {"hito","pantalla_esperada"} o strings."""
    out: list[Milestone] = []
    for item in (parsed or {}).get("plan") or []:
        if isinstance(item, dict):
            text = str(item.get("hito") or item.get("milestone") or "").strip()
            expected = str(item.get("pantalla_esperada") or item.get("expected") or "").strip()
            locate = str(item.get("localiza_registro") or item.get("locate") or "").strip()
            if locate.lower() in ("null", "none"):
                locate = ""
        else:
            text, expected, locate = str(item).strip(), "", ""
        if text:
            out.append(Milestone(text, expected, locate))
    return out


async def plan(client, task: str) -> list[Milestone]:
    """Captura la pantalla, lee su texto (OCR) y devuelve hitos de alto nivel.

    Reintenta una vez si la respuesta viene sin hitos (flakiness observado del
    modelo de texto), antes de ceder al fallback del loop (`[task]`).
    """
    frame = await wait_and_capture(client)
    try:
        context = await extract_text(frame)
    except Exception:
        context = ""
    model = select(Capability.PLAN) or select(Capability.HARD) or "deepseek/deepseek-v4-flash"
    prompt = load_prompt("plan", task=task, context=context)
    for _ in range(2):
        res = await chat(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            model,
            json_mode=True,
            max_tokens=768,
        )
        hitos = parse_plan(res.parsed)
        rejection = parse_rejection(res.parsed)
        if rejection and not hitos:
            trace("plan.rechazo", motivo=rejection)
            raise TaskRejected(rejection)
        if hitos:
            trace("plan", hitos=[(h.text, h.expected) for h in hitos], ocr=context[:300])
            return hitos
    trace("plan.vacio")
    return []
