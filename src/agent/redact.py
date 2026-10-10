"""Redactor de secretos: nunca dejar password/token/API key en un resumen o log."""

from __future__ import annotations

import os

REDACTED = "<REDACTED>"

_ENV_KEYS = ("OPENROUTER_API_KEY", "TEAM_TOKEN")


def env_secrets() -> list[str]:
    """Valores sensibles presentes en el entorno (API keys, tokens)."""
    return [v for k in _ENV_KEYS if (v := os.environ.get(k))]


def redact_text(text: str, secrets=()) -> str:
    """Reemplaza valores sensibles por <REDACTED> (se omite lo trivial, <4 chars)."""
    result = str(text)
    for secret in [*secrets, *env_secrets()]:
        s = str(secret)
        if len(s) >= 4:
            result = result.replace(s, REDACTED)
    return result
