"""Ejecución de acciones (coords o por etiqueta de elemento) sobre el escritorio."""

from __future__ import annotations

import unicodedata

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
    """Convierte coords a píxeles, aceptando normalizadas 0-1 o píxeles absolutos.

    Los modelos de grounding son inconsistentes: a veces devuelven fracciones
    (0.15) y a veces píxeles (156). Se auto-detecta: valor en [-1.5, 1.5] se
    interpreta como fracción; si no, como píxel absoluto. Luego se clamp.
    """
    def conv(v, size: int) -> int:
        f = float(v)
        if -1.5 <= f <= 1.5:
            return int(f * size)
        return int(f)

    px = max(0, min(width - 1, conv(x, width)))
    py = max(0, min(height - 1, conv(y, height)))
    return px, py


def normalize_text(s: str) -> str:
    """Normaliza para comparar etiquetas: sin acentos, minúsculas, espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().split())


def find_element(elements, target: str):
    """Busca un elemento por etiqueta (exacta, luego substring en ambos sentidos)."""
    t = normalize_text(target)
    if not t or not elements:
        return None
    for el in elements:
        if normalize_text(el.text) == t:
            return el
    for el in elements:
        e = normalize_text(el.text)
        if e and (t in e or e in t):
            return el
    return None


async def execute_actions(
    client,
    actions,
    width: int,
    height: int,
    *,
    elements=None,
    max_actions: int = 8,
) -> int:
    """Ejecuta una lista de acciones y devuelve cuántas ejecutó.

    `elements` es la lista de elementos detectados (para resolver `click_text`).
    """
    executed = 0
    for action in (actions or [])[:max_actions]:
        op = str(action.get("op") or "").strip().lower()
        if op == "click":
            x, y = normalize_coords(action.get("x", 0), action.get("y", 0), width, height)
            await click(client, x, y)
        elif op == "click_text":
            el = find_element(elements, str(action.get("text", "")))
            if el is not None:
                await click(client, el.x, el.y)
            else:
                continue
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
