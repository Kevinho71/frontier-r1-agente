"""Ejecución de acciones (coords o por etiqueta de elemento) sobre el escritorio."""

from __future__ import annotations

import unicodedata

from desktop.input import click, press_key, select_all, type_text, wait_ms

from .trace import trace

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
    """Normaliza para comparar etiquetas: sin acentos ni puntuación, minúsculas, espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
    return " ".join(s.lower().split())


def find_element(elements, target: str):
    """Busca un elemento por etiqueta: exacta; si no, la substring más cercana en longitud.

    Evita que "Nombre:" (campo) se confunda con "Nombres" (menú): la coincidencia
    exacta gana, y entre parciales gana la etiqueta de longitud más parecida.
    """
    t = normalize_text(target)
    if not t or not elements:
        return None
    for el in elements:
        if normalize_text(el.text) == t:
            return el
    best = None
    best_gap = None
    for el in elements:
        e = normalize_text(el.text)
        if e and (t in e or e in t):
            gap = abs(len(e) - len(t))
            if best_gap is None or gap < best_gap:
                best, best_gap = el, gap
    return best


def resolve_element(elements, index=None, text: str = ""):
    """Resuelve un elemento por índice 1-based (lista numerada del prompt) o por etiqueta.

    El índice es inequívoco; la etiqueta es el respaldo. Si ambos vienen y el
    índice apunta a un elemento cuya etiqueta no se parece a `text`, manda la etiqueta.
    """
    if not elements:
        return None
    by_index = None
    try:
        i = int(index)
        if 1 <= i <= len(elements):
            by_index = elements[i - 1]
    except (TypeError, ValueError):
        pass
    if by_index is not None:
        if not text or normalize_text(text) in normalize_text(by_index.text) or normalize_text(by_index.text) in normalize_text(text):
            return by_index
    return find_element(elements, text) if text else by_index


async def execute_actions(
    client,
    actions,
    width: int,
    height: int,
    *,
    elements=None,
    max_actions: int = 16,
    auto_select_all: bool = True,
) -> int:
    """Ejecuta una lista de acciones y devuelve cuántas ejecutó.

    `elements` es la lista de elementos detectados (para resolver `click_text`).
    """
    executed = 0
    last_op = ""
    for action in (actions or [])[:max_actions]:
        if not isinstance(action, dict):
            continue
        try:
            done_op = await _run_action(client, action, width, height, elements, auto_select_all, last_op)
        except Exception as exc:  # una acción inválida (p. ej. tecla inventada) no debe tumbar la tarea
            trace("action.error", action=action, err=repr(exc))
            continue
        if done_op:
            executed += 1
            last_op = done_op
    return executed


async def _run_action(client, action, width, height, elements, auto_select_all, last_op) -> str:
    """Ejecuta UNA acción; devuelve su `op` si se ejecutó, o "" si se omitió."""
    op = str(action.get("op") or "").strip().lower()
    if op == "click":
        x, y = normalize_coords(action.get("x", 0), action.get("y", 0), width, height)
        await click(client, x, y)
    elif op == "click_text":
        el = resolve_element(elements, action.get("index"), str(action.get("text", "")))
        if el is None:
            return ""
        await click(client, el.x, el.y)
    elif op == "type":
        # Escribir sobre un campo con texto concatena: Ctrl+A antes hace el tecleo
        # idempotente (reintentos del mismo lote no duplican el valor).
        if auto_select_all and last_op != "select_all":
            await select_all(client)
        await type_text(client, str(action.get("text", "")))
    elif op == "press":
        await press_key(client, normalize_key(str(action.get("key", "Enter"))))
    elif op == "select_all":
        await select_all(client)
    elif op == "wait":
        await wait_ms(int(action.get("ms", 800)))
    else:
        return ""
    return op
