"""Planificación inicial: OCR barato + modelo de texto → hitos."""

from __future__ import annotations

from desktop.capture import wait_and_capture
from model import Capability, chat, load_prompt, select
from vision.ocr import extract_text


async def plan(client, task: str) -> list[str]:
    """Captura la pantalla, lee su texto (OCR) y devuelve hitos de alto nivel."""
    frame = await wait_and_capture(client)
    try:
        context = await extract_text(frame)
    except Exception:
        context = ""
    model = select(Capability.PLAN) or select(Capability.HARD) or "deepseek/deepseek-v4-flash"
    prompt = load_prompt("plan", task=task, context=context)
    res = await chat(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        model,
        json_mode=True,
        max_tokens=512,
    )
    parsed = res.parsed or {}
    return [str(h) for h in (parsed.get("plan") or [])]
