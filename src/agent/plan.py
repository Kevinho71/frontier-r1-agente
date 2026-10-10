"""Planificación inicial: OCR barato + modelo de texto → hitos."""

from __future__ import annotations

from desktop.capture import wait_and_capture
from model import Capability, chat, load_prompt, select
from vision.ocr import extract_text


async def plan(client, task: str) -> list[str]:
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
            max_tokens=512,
        )
        parsed = res.parsed or {}
        hitos = [str(h) for h in (parsed.get("plan") or [])]
        if hitos:
            return hitos
    return []
