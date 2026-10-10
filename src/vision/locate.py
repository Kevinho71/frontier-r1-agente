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


# Qwen3-VL devuelve coordenadas relativas en 0-1000 (no fracciones ni píxeles).
# Verificado contra la pantalla real: Buscar (382,130)px ↔ (298,162) en 0-1000.
_SCALE_1000_PREFIXES = ("qwen/qwen3-vl",)


def scale_for(model: str) -> int | None:
    """Escala nativa de coordenadas del modelo (1000) o None si es fracción/píxel."""
    return 1000 if str(model).startswith(_SCALE_1000_PREFIXES) else None


def _to_px(v: float, size: int, scale: int | None = None) -> float:
    """Convierte un valor de caja a píxeles.

    Con `scale` (p. ej. 1000) el valor es relativo a esa escala; si todo el box es
    una fracción 0-1 (el modelo obedeció el prompt) también se acepta. Sin `scale`,
    acepta fracción 0-1 o píxel absoluto.
    """
    if scale:
        return v * size / scale if abs(v) > 1.5 else v * size
    return v * size if -1.5 <= v <= 1.5 else v


def _box_center(box, w: int, h: int, scale: int | None = None) -> tuple[int, int]:
    x1, y1, x2, y2 = (float(v) for v in box)
    if scale and max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
        scale = None  # el modelo devolvió fracciones 0-1 pese al prompt
        cx = (x1 + x2) / 2 * w
        cy = (y1 + y2) / 2 * h
        return int(cx), int(cy)
    cx = (_to_px(x1, w, scale) + _to_px(x2, w, scale)) / 2
    cy = (_to_px(y1, h, scale) + _to_px(y2, h, scale)) / 2
    return int(cx), int(cy)


def parse_item(it) -> tuple[str, list]:
    """Acepta {"text","box"} o la forma compacta [texto, x1, y1, x2, y2]."""
    if isinstance(it, dict):
        return str(it.get("text") or "").strip(), list(it.get("box") or [])
    if isinstance(it, (list, tuple)) and len(it) == 5:
        return str(it[0] or "").strip(), list(it[1:])
    return "", []


async def detect_elements(frame, model: str = DETECTOR_MODEL) -> tuple[list[Element], float]:
    """Detecta los elementos interactivos de la pantalla; devuelve (elementos, cost_usd)."""
    prompt = load_prompt("detect")
    res = await chat_vision(
        prompt,
        frame,
        model,
        downscale_to=None,
        json_mode=True,
        max_tokens=1200,
        provider={"sort": "latency"},  # el detector domina la latencia: prioriza el proveedor más rápido
    )
    items = (res.parsed or {}).get("items") or []
    h, w = frame.shape[:2]
    scale = scale_for(model)
    elements: list[Element] = []
    for it in items:
        text, box = parse_item(it)
        if not text or len(box) != 4:
            continue
        cx, cy = _box_center(box, w, h, scale)
        elements.append(Element(text=text, x=cx, y=cy))
    return elements, res.cost_usd
