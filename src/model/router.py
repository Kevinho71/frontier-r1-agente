"""Routing de modelos por capacidad, con agotamiento en memoria.

Regla de cuota (aprendida en la práctica): ante 429 con `retryable:false` (cuota
agotada) o 404 (modelo inexistente), el modelo se marca `exhausted` y se excluye
del routing por el resto del proceso. El contenedor es persistente, así que el
set en memoria equivale a "el resto del día" durante la evaluación.
"""

from __future__ import annotations

from .registry import CANDIDATES, Capability

_exhausted: set[str] = set()


def select(
    capability: Capability, *, exclude: set[str] | None = None
) -> str | None:
    """Devuelve el primer modelo no agotado para la capacidad, o None si todos lo están."""
    for model_id in CANDIDATES.get(capability, []):
        if model_id in _exhausted:
            continue
        if exclude and model_id in exclude:
            continue
        return model_id
    return None


def mark_exhausted(model_id: str) -> None:
    _exhausted.add(model_id)


def is_exhausted(model_id: str) -> bool:
    return model_id in _exhausted


def reset() -> None:
    _exhausted.clear()
