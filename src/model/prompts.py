"""Carga de plantillas de prompt desde prompts/*.txt.

Los placeholders usan dobles llaves `{{var}}` para no chocar con las llaves del
JSON que los prompts devuelven como ejemplo.
"""

from __future__ import annotations

import os

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_prompt(name: str, **vars_) -> str:
    """Lee prompts/<name>.txt y sustituye `{{var}}` por los valores pasados."""
    path = os.path.join(_PROMPT_DIR, f"{name}.txt")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for key, value in vars_.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
