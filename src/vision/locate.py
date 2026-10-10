"""Vision: localización de elementos interactivos con bounding boxes (grounding por detección).

El grounding por coordenadas (regresión de un punto) es impreciso; en su lugar un
VLM detecta los elementos con sus cajas y el agente clica el CENTRO de la caja del
elemento elegido por etiqueta. Ver docs/fase_4_hotfix_grounding.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from model import chat_vision, load_prompt

# Modelo detector (validado en vivo: devuelve boxes normalizadas correctas).
# qwen3-vl-30b devuelve boxes en píxeles y mal ubicadas; 235b/72b son correctas.
DETECTOR_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"


@dataclass
class Element:
    text: str
    x: int  # centro en píxeles
    y: int  # centro en píxeles


def _to_px(v: float, size: int) -> float:
    """Acepta fracción 0-1 o píxel absoluto."""
    return v * size if -1.5 <= v <= 1.5 else v


def _box_center(box, w: int, h: int) -> tuple[int, int]:
    x1, y1, x2, y2 = (float(v) for v in box)
    cx = (_to_px(x1, w) + _to_px(x2, w)) / 2
    cy = (_to_px(y1, h) + _to_px(y2, h)) / 2
    return int(cx), int(cy)


async def detect_elements(frame, model: str = DETECTOR_MODEL) -> tuple[list[Element], float]:
    """Detecta los elementos interactivos de la pantalla; devuelve (elementos, cost_usd)."""
    prompt = load_prompt("detect")
    res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=1200)
    items = (res.parsed or {}).get("items") or []
    h, w = frame.shape[:2]
    elements: list[Element] = []
    for it in items:
        text = str(it.get("text") or "").strip()
        box = it.get("box") or []
        if not text or len(box) != 4:
            continue
        cx, cy = _box_center(box, w, h)
        elements.append(Element(text=text, x=cx, y=cy))
    return elements, res.cost_usd
