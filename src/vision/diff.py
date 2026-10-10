"""Vision: deteccion de cambios entre capturas por hash y diff de pixeles."""

import hashlib

import numpy as np


def frame_signature(frame: np.ndarray, box: tuple | None = None) -> str:
    """Hash estable de un frame (o region) para registrar cambios."""
    region = frame if box is None else _slice(frame, box)
    arr = np.asarray(region)
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    small = np.asarray(_to_thumb(arr))
    return hashlib.sha256(small.tobytes()).hexdigest()[:16]


def diff_fraction(a: np.ndarray, b: np.ndarray, box: tuple | None = None) -> float:
    """Fraccion de pixeles que cambiaron entre dos capturas (0..1)."""
    ra = _gray(a if box is None else _slice(a, box))
    rb = _gray(b if box is None else _slice(b, box))
    if ra.shape != rb.shape:
        return 1.0
    return float(np.mean(np.abs(ra.astype(np.float32) - rb.astype(np.float32))) / 255.0)


def changed(a: np.ndarray, b: np.ndarray, box: tuple | None = None, threshold: float = 0.001) -> bool:
    """True si la pantalla cambió más allá del umbral (default 0.1% de píxeles).

    Nota: un cambio pequeño (ej. un menú desplegado) afecta una fracción chica
    de la pantalla; el 'no cambio' real da exactamente 0.0, así que 0.1% es
    sensible sin falsos positivos.
    """
    return diff_fraction(a, b, box) > threshold


def _slice(frame: np.ndarray, box: tuple) -> np.ndarray:
    x, y, w, h = box
    return np.asarray(frame)[y : y + h, x : x + w]


def _gray(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        arr = np.mean(arr.astype(np.float32), axis=2)
    return arr


def _to_thumb(arr: np.ndarray, size: int = 32) -> np.ndarray:
    """Minuscula imagen para hash rapido sin PIL."""
    h, w = arr.shape[:2]
    if arr.ndim == 3:
        arr = np.mean(arr.astype(np.float32), axis=2)
    step_h = max(1, h // size)
    step_w = max(1, w // size)
    return arr[::step_h, ::step_w].astype(np.uint8)