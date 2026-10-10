"""Actuación: detecta elementos → decide acción por etiqueta → ejecuta.

Flujo preferido (grounding por detección): un VLM detecta los elementos con sus
bounding boxes (fiable), y un modelo de texto elige QUÉ elemento tocar (barato).
El clic se hace en el centro de la caja detectada, no en una coordenada adivinada.
Si la detección falla, cae al grounding por visión (coordenadas).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from desktop.capture import wait_and_capture
from model import Capability, chat, chat_vision, load_prompt, select
from vision.locate import detect_elements

from .actions import execute_actions


@dataclass
class ActResult:
    frame_after: np.ndarray
    actions_executed: int
    cost_usd: float


def _format_elements(elements) -> str:
    els = sorted(elements, key=lambda e: (e.y // 30, e.x))
    return "\n".join(f'{i + 1}. "{e.text}"' for i, e in enumerate(els))


async def act(client, task: str, milestone: str, *, max_actions: int = 8) -> ActResult:
    """Pide al agente un batch de acciones y lo ejecuta sobre el escritorio."""
    frame = await wait_and_capture(client)
    h, w = frame.shape[:2]
    cost = 0.0

    elements = []
    try:
        elements, detect_cost = await detect_elements(frame)
        cost += detect_cost
    except Exception:
        elements = []

    if elements:
        # decisión por etiqueta (barata, modelo de texto)
        model = select(Capability.PLAN) or "deepseek/deepseek-v4-flash"
        prompt = load_prompt(
            "select",
            task=task,
            milestone=milestone,
            elements=_format_elements(elements),
        )
        res = await chat(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            model,
            json_mode=True,
            max_tokens=512,
        )
        cost += res.cost_usd
        actions = (res.parsed or {}).get("actions") or []
    else:
        # fallback: grounding por visión con coordenadas
        model = select(Capability.GROUND) or select(Capability.HARD)
        prompt = load_prompt("ground", task=task, milestone=milestone)
        res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=512)
        cost += res.cost_usd
        actions = (res.parsed or {}).get("actions") or []

    executed = await execute_actions(client, actions, w, h, elements=elements, max_actions=max_actions)
    frame_after = await wait_and_capture(client)
    return ActResult(frame_after, executed, cost)
