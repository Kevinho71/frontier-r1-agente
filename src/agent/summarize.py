"""Resumen final con formato exacto + redacción de secretos."""

from __future__ import annotations

from model import Capability, chat_vision, load_prompt, select

from .redact import redact_text

_QUESTION_WORDS = (
    "cuánt",
    "cuant",
    "cuál",
    "cual",
    "cuánto",
    "cuanto",
    "cuántas",
    "cuantas",
    "cuántos",
    "cuantos",
    "dime",
)


def is_question(task: str) -> bool:
    """Heurística simple: ¿la tarea pide un dato (respuesta), no una acción?"""
    t = task.strip()
    if "?" in t:
        return True
    low = t.lower()
    return any(w in low for w in _QUESTION_WORDS)


async def extract_answer(task: str, frame) -> str | None:
    """Extrae la respuesta (número/dato) de la pantalla para tareas de pregunta."""
    model = select(Capability.CHECK) or select(Capability.HARD)
    prompt = load_prompt("answer", task=task)
    res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=128)
    parsed = res.parsed or {}
    value = parsed.get("respuesta") or parsed.get("answer") or parsed.get("valor")
    return str(value).strip() if value not in (None, "") else None


def format_summary(
    task,
    *,
    estado: str,
    answer: str | None = None,
    reason: str = "",
    steps: int = 0,
    cost_usd: float = 0.0,
    secrets=(),
) -> str:
    """Arma el resumen: la línea `respuesta:` con el número primero, sin secretos."""
    lines = [f"Tarea: {task}"]
    if answer:
        lines.append(f"respuesta: {answer}")
    if reason:
        lines.append(f"Motivo: {reason}")
    lines.append(f"Estado: {estado} · Pasos: {steps} · Costo: ${cost_usd:.5f}")
    return redact_text("\n".join(lines), secrets)
