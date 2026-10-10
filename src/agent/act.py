"""Actuación: GROUND (visión) → lista de acciones → ejecutar sobre el escritorio."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from desktop.capture import wait_and_capture
from model import Capability, chat_vision, load_prompt, select

from .actions import execute_actions


@dataclass
class ActResult:
    frame_after: np.ndarray
    actions_executed: int
    cost_usd: float


async def act(client, task: str, milestone: str, *, max_actions: int = 8) -> ActResult:
    """Pide al modelo de grounding un batch de acciones y lo ejecuta.

    El grounding NO decide si el hito está completo: solo propone acciones; la
    compleción la verifica `check()` en el loop.
    """
    frame = await wait_and_capture(client)
    h, w = frame.shape[:2]
    model = select(Capability.GROUND) or select(Capability.HARD)
    prompt = load_prompt("ground", task=task, milestone=milestone)
    # Resolución completa: el grounding devuelve píxeles absolutos; sin downscale
    # no hay ambigüedad de escala al convertir coords.
    res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=512)
    parsed = res.parsed or {}
    actions = parsed.get("actions") or []
    executed = await execute_actions(client, actions, w, h, max_actions=max_actions)
    frame_after = await wait_and_capture(client)
    return ActResult(frame_after, executed, res.cost_usd)
