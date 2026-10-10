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
    done: bool
    actions_executed: int
    cost_usd: float


async def act(client, task: str, milestone: str, *, max_actions: int = 8) -> ActResult:
    """Pide al modelo de grounding un batch de acciones y lo ejecuta."""
    frame = await wait_and_capture(client)
    h, w = frame.shape[:2]
    model = select(Capability.GROUND) or select(Capability.HARD)
    prompt = load_prompt("ground", task=task, milestone=milestone)
    res = await chat_vision(prompt, frame, model, downscale_to=800, json_mode=True, max_tokens=512)
    parsed = res.parsed or {}
    done = bool(parsed.get("done"))
    actions = parsed.get("actions") or []
    executed = await execute_actions(client, actions, w, h, max_actions=max_actions)
    frame_after = await wait_and_capture(client)
    return ActResult(frame_after, done, executed, res.cost_usd)
