"""Traza de depuración opcional (RETO1_TRACE=1). Todo pasa por el redactor de secretos."""

from __future__ import annotations

import os
import sys
import time

from .redact import redact_text

_T0 = time.monotonic()


def enabled() -> bool:
    return os.environ.get("RETO1_TRACE", "") not in ("", "0", "false")


def trace(event: str, **data) -> None:
    """Imprime una línea de traza en stderr si RETO1_TRACE está activo."""
    if not enabled():
        return
    body = " ".join(f"{k}={v!r}" for k, v in data.items())
    line = f"[trace +{time.monotonic() - _T0:6.1f}s] {event} {body}"
    print(redact_text(line), file=sys.stderr, flush=True)
