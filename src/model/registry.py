"""Catálogo de modelos por capacidad (fuente única de verdad) y precios.

Los IDs y precios son defaults; deben verificarse contra el catálogo vivo de
OpenRouter antes de la evaluación (ver spikes/model_test.py). El costo por
imagen se factura distinto en OpenRouter, así que el precio aquí es aproximado
para la estimación de `cost_usd`.
"""

from __future__ import annotations

from enum import Enum


class Capability(Enum):
    PLAN = "plan"
    GROUND = "ground"
    CHECK = "check"
    HARD = "hard"


# candidatos ordenados por preferencia (primario primero, luego fallbacks)
# Nota: CHECK usa qwen (soporta json_object); ling-3.0-flash-vl devuelve vacío
# con response_format=json_object, por eso quedó SOLO para OCR (json_mode=False).
# GROUND usa qwen primero: ui-tars-1.5-7b devuelve coords en píxeles (no 0-1) y
# apunta al menú equivocado; se mantiene como último fallback barato.
CANDIDATES: dict[Capability, list[str]] = {
    Capability.PLAN: ["deepseek/deepseek-v4-flash"],
    Capability.GROUND: [
        "qwen/qwen3-vl-30b-a3b-instruct",
        "qwen/qwen3-vl-235b-a22b-instruct",
        "bytedance/ui-tars-1.5-7b",
    ],
    Capability.CHECK: [
        "qwen/qwen3-vl-30b-a3b-instruct",
        "qwen/qwen3-vl-235b-a22b-instruct",
    ],
    Capability.HARD: [
        "qwen/qwen3-vl-30b-a3b-instruct",
        "qwen/qwen3-vl-235b-a22b-instruct",
    ],
}

# precio $/M tokens: (in, out)
PRICES: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4-flash": (0.03, 1.28),
    "bytedance/ui-tars-1.5-7b": (0.10, 0.20),
    "inclusionai/ling-3.0-flash-vl": (0.021, 0.062),
    "qwen/qwen3-vl-30b-a3b-instruct": (0.15, 0.60),
    "qwen/qwen3-vl-235b-a22b-instruct": (0.21, 1.90),
}


def price_for(model_id: str) -> tuple[float, float]:
    """Precio (in, out) en $/M tokens; (0.0, 0.0) si el modelo no está en el catálogo."""
    return PRICES.get(model_id, (0.0, 0.0))
