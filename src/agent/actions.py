"""Ejecución de acciones normalizadas (coords 0-1) sobre el escritorio."""

from __future__ import annotations

from desktop.input import click, press_key, select_all, type_text, wait_ms

_KEY_ALIASES = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
}


def normalize_key(key: str) -> str:
    """Traduce alias comunes a los keysyms que espera asyncvnc."""
    return _KEY_ALIASES.get(str(key).strip().lower(), key)


def normalize_coords(x, y, width: int, height: int) -> tuple[int, int]:
    """Convierte coords normalizadas 0-1 a píxeles, clampadas al viewport."""
    px = max(0, min(width - 1, int(float(x) * width)))
    py = max(0, min(height - 1, int(float(y) * height)))
    return px, py


async def execute_actions(client, actions, width: int, height: int, *, max_actions: int = 8) -> int:
    """Ejecuta una lista de acciones del GROUND y devuelve cuántas ejecutó."""
    executed = 0
    for action in (actions or [])[:max_actions]:
        op = str(action.get("op") or "").strip().lower()
        if op == "click":
            x, y = normalize_coords(action.get("x", 0), action.get("y", 0), width, height)
            await click(client, x, y)
        elif op == "type":
            await type_text(client, str(action.get("text", "")))
        elif op == "press":
            await press_key(client, normalize_key(str(action.get("key", "Enter"))))
        elif op == "select_all":
            await select_all(client)
        elif op == "wait":
            await wait_ms(int(action.get("ms", 800)))
        else:
            continue
        executed += 1
    return executed
