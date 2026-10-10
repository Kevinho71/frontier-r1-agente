"""Actuación: detecta elementos → decide acción por etiqueta → ejecuta.

Flujo preferido (grounding por detección): un VLM detecta los elementos con sus
bounding boxes (fiable), y un modelo de texto elige QUÉ elemento tocar (barato).
El clic se hace en el centro de la caja detectada, no en una coordenada adivinada.
Si la detección falla, cae al grounding por visión (coordenadas).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from desktop.capture import wait_and_capture
from model import Capability, chat, chat_vision, load_prompt, select
from vision.locate import detect_elements

from .actions import allows_retry, execute_actions, is_commit_label, normalize_text, resolve_element
from .trace import trace


@dataclass
class ActState:
    """Memoria entre llamadas a act(): evita reabrir/cerrar el mismo menú (toggle)."""

    last_labels: set = field(default_factory=set)
    last_click: str = ""
    committed: list = field(default_factory=list)  # (etiqueta, x, y) de botones de confirmación ya pulsados

    def blocked(self, el, feedback: str = "") -> bool:
        """¿Volver a pulsar este botón de confirmación duplicaría el efecto?

        Se bloquea el MISMO botón (misma etiqueta y posición) ya pulsado, salvo que la
        verificación reporte un error de validación (el envío no llegó a hacerse).
        """
        if allows_retry(feedback):
            return False
        label = normalize_text(el.text)
        return any(label == c[0] and abs(el.x - c[1]) < 25 and abs(el.y - c[2]) < 25 for c in self.committed)

    def record(self, actions, elements) -> None:
        for a in actions or []:
            if str(a.get("op")) != "click_text":
                continue
            el = resolve_element(elements, a.get("index"), str(a.get("text", "")))
            if el is not None and is_commit_label(el.text):
                self.committed.append((normalize_text(el.text), el.x, el.y))


@dataclass
class ActResult:
    frame_after: np.ndarray
    actions_executed: int
    cost_usd: float
    description: str = ""


def sort_elements(elements) -> list:
    """Orden de lectura (filas de 30px, izquierda→derecha); el índice del prompt sale de aquí."""
    return sorted(elements, key=lambda e: (e.y // 30, e.x))


def _format_elements(els) -> str:
    return "\n".join(f'{i + 1}. "{e.text}"' for i, e in enumerate(els))


def describe_actions(actions) -> str:
    """Resumen corto de un batch de acciones para el historial."""
    parts = []
    for a in actions or []:
        op = str(a.get("op") or "")
        if op == "click_text":
            parts.append(f'clic "{a.get("text", "")}"')
        elif op == "type":
            parts.append(f'escribir "{a.get("text", "")}"')
        elif op == "press":
            parts.append(f'tecla {a.get("key", "")}')
        elif op in ("select_all", "click"):
            parts.append(op)
    return ", ".join(parts)


async def act(
    client,
    task: str,
    milestone: str,
    *,
    expected: str = "",
    history=None,
    feedback: str = "",
    state: ActState | None = None,
    prefetched=None,
    max_actions: int = 16,
) -> ActResult:
    """Pide al agente un batch de acciones y lo ejecuta sobre el escritorio.

    `prefetched` = (frame, tarea de detect_elements sobre ese frame): la detección de la
    pantalla actual se lanzó en paralelo con el check anterior (ahorra su latencia).
    """
    t_start = time.monotonic()
    cost = 0.0
    elements = []
    try:
        if prefetched is not None:
            frame, det_task = prefetched
            elements, detect_cost = await det_task
        else:
            frame = await wait_and_capture(client)
            elements, detect_cost = await detect_elements(frame)
        cost += detect_cost
    except Exception:
        elements = []
    h, w = frame.shape[:2]
    t_detect = time.monotonic() - t_start
    labels = {normalize_text(e.text) for e in elements}
    avoid = ""
    if state is not None and state.last_click:
        # Si tras el último clic aparecieron elementos nuevos (se abrió un menú),
        # volver a clicar ese mismo elemento lo cerraría: se excluye de las opciones.
        if labels - state.last_labels:
            avoid = state.last_click
            elements = [e for e in elements if normalize_text(e.text) != avoid]
    had_elements = bool(elements)
    if state is not None and state.committed:
        kept = [e for e in elements if not state.blocked(e, feedback)]
        if len(kept) != len(elements):
            trace("guard.duplicado", bloqueados=[e.text for e in elements if e not in kept])
        elements = kept
    elements = sort_elements(elements)

    if elements:
        # decisión por etiqueta (barata, modelo de texto)
        model = select(Capability.PLAN) or "deepseek/deepseek-v4-flash"
        prompt = load_prompt(
            "select",
            task=task,
            milestone=milestone,
            expected=expected or "(no especificada)",
            history="\n".join(f"- {line}" for line in (history or [])[-6:]) or "(ninguna)",
            feedback=(feedback or "(aún no hay verificación)")
            + (f'\nNOTA: el elemento "{avoid}" ya fue clicado y su menú está abierto; ya no aparece en la lista. Elige una de las opciones nuevas, o abre otro menú de nivel superior.' if avoid else ""),
            elements=_format_elements(elements),
        )
        res = await chat(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            model,
            json_mode=True,
            max_tokens=768,
        )
        cost += res.cost_usd
        actions = (res.parsed or {}).get("actions") or []
    elif had_elements:
        actions = []  # todo lo detectado era un botón de confirmación ya pulsado: no hacer nada
    else:
        # fallback: grounding por visión con coordenadas
        model = select(Capability.GROUND) or select(Capability.HARD)
        prompt = load_prompt("ground", task=task, milestone=milestone)
        res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=512)
        cost += res.cost_usd
        actions = (res.parsed or {}).get("actions") or []

    t_total = time.monotonic() - t_start
    trace(
        "act",
        milestone=milestone,
        elements=[e.text for e in elements],
        avoid=avoid,
        actions=actions,
        detect_s=round(t_detect, 1),
        total_s=round(t_total, 1),
    )
    if state is not None:
        state.last_labels = labels
        state.last_click = ""
        for a in actions or []:
            if str(a.get("op")) == "click_text":
                state.last_click = normalize_text(a.get("text", ""))
        state.record(actions, elements)
    executed = await execute_actions(client, actions, w, h, elements=elements, max_actions=max_actions)
    frame_after = await wait_and_capture(client)
    return ActResult(frame_after, executed, cost, describe_actions(actions))
