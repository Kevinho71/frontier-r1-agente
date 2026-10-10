"""Traza de depuración opcional (RETO1_TRACE=1). Todo pasa por el redactor de secretos."""

from __future__ import annotations

import os
import sys
import time

from .redact import redact_text

_T0 = time.monotonic()


def enabled() -> bool:
    return os.environ.get("RETO1_TRACE", "") not in ("", "0", "false")


_DUMP_N = 0


def dump_frame(frame, tag: str = "") -> None:
    """Guarda el frame en RETO1_DUMP=<dir> (depuración; no contiene secretos del servicio)."""
    global _DUMP_N
    d = os.environ.get("RETO1_DUMP", "")
    if not d:
        return
    try:
        from PIL import Image

        os.makedirs(d, exist_ok=True)
        _DUMP_N += 1
        Image.fromarray(frame).convert("RGB").save(os.path.join(d, f"{_DUMP_N:03d}_{tag}.png"))
    except Exception:
        pass


def trace(event: str, **data) -> None:
    """Imprime una línea de traza en stderr si RETO1_TRACE está activo."""
    if not enabled():
        return
    body = " ".join(f"{k}={v!r}" for k, v in data.items())
    line = f"[trace +{time.monotonic() - _T0:6.1f}s] {event} {body}"
    print(redact_text(line), file=sys.stderr, flush=True)
