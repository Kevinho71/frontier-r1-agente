"""Planificación inicial: OCR barato + modelo de texto → hitos."""

from __future__ import annotations

from desktop.capture import wait_and_capture
from model import Capability, chat, load_prompt, select
from vision.ocr import extract_text

from .trace import trace
from .types import Milestone


def parse_plan(parsed) -> list[Milestone]:
    """Convierte la respuesta del modelo en hitos. Acepta {"hito","pantalla_esperada"} o strings."""
    out: list[Milestone] = []
    for item in (parsed or {}).get("plan") or []:
        if isinstance(item, dict):
            text = str(item.get("hito") or item.get("milestone") or "").strip()
            expected = str(item.get("pantalla_esperada") or item.get("expected") or "").strip()
        else:
            text, expected = str(item).strip(), ""
        if text:
            out.append(Milestone(text, expected))
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
        if hitos:
            trace("plan", hitos=[(h.text, h.expected) for h in hitos], ocr=context[:300])
            return hitos
    trace("plan.vacio")
    return []
