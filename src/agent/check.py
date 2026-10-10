"""Verificación de hitos: diff (barato) + OCR (contexto) + LLM visión (veredicto)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from desktop.capture import wait_and_capture
from model import Capability, chat_vision, load_prompt, select
from vision.diff import changed as frame_changed
from vision.ocr import extract_text

from .trace import trace


@dataclass
class CheckResult:
    ok: bool
    description: str
    changed: bool
    cost_usd: float


async def check(client, task: str, milestone: str, prev_frame, expected: str = "", *, frame=None) -> CheckResult:
    """¿Se cumplió el hito? diff global + OCR de contexto + veredicto por visión."""
    t0 = time.monotonic()
    # Reutiliza la captura que act() ya tomó tras esperar el repintado (ahorra ~1s+).
    cur = frame if frame is not None else await wait_and_capture(client)
    changed_flag = frame_changed(prev_frame, cur) if prev_frame is not None else True
    try:
        ocr_text = await extract_text(cur)
    except Exception:
        ocr_text = ""
    model = select(Capability.CHECK) or select(Capability.HARD)
    prompt = load_prompt("check", task=task, milestone=milestone, expected=expected or "(no especificada)")
    if ocr_text:
        prompt = f"{prompt}\n\nTexto OCR visible:\n{ocr_text}"
    res = await chat_vision(prompt, cur, model, downscale_to=None, json_mode=True, max_tokens=256)
    parsed = res.parsed or {}
    ok = bool(parsed.get("ok"))
    desc = str(parsed.get("description", ""))
    trace("check", milestone=milestone, ok=ok, desc=desc, total_s=round(time.monotonic() - t0, 1))
    return CheckResult(ok, desc, changed_flag, res.cost_usd)
