"""Resumen final con formato exacto + redacción de secretos."""

from __future__ import annotations

import asyncio

from model import Capability, chat_text, chat_vision, load_prompt, select

from .redact import redact_text
from .trace import trace

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


def parse_answer(parsed) -> dict | None:
    """Normaliza la respuesta del modelo: {"tipo","respuesta","filas","total","mas"}."""
    if not isinstance(parsed, dict):
        return None
    tipo = str(parsed.get("tipo") or "").strip().lower()
    filas = [str(f).strip() for f in (parsed.get("filas") or []) if str(f).strip()]
    total = parsed.get("total_visible")
    try:
        total = int(str(total).replace(".", "").strip()) if total not in (None, "", "null") else None
    except ValueError:
        total = None
    value = parsed.get("respuesta")
    if value is None:
        value = parsed.get("answer") if parsed.get("answer") is not None else parsed.get("valor")
    if value is not None and str(value).strip().lower() in ("", "null", "none"):
        value = None
    if not tipo:
        tipo = "conteo" if filas or total is not None else "dato"
    return {
        "tipo": tipo,
        "respuesta": str(value).strip() if value is not None else None,
        "filas": filas,
        "total": total,
        "mas": bool(parsed.get("hay_mas_paginas")),
    }


async def _ask_answer(task: str, frame) -> dict | None:
    model = select(Capability.CHECK) or select(Capability.HARD)
    prompt = load_prompt("answer", task=task)
    res = await chat_vision(prompt, frame, model, downscale_to=None, json_mode=True, max_tokens=700)
    trace("answer.raw", raw=res.content[:600])
    return parse_answer(res.parsed)


# Transcribir una tabla requiere un modelo fuerte: 30b omite/confunde filas (medido contra
# la verdad de terreno en spikes/table_bench.py: 235b y 72b exactos, 30b no).
TABLE_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"

_COUNT_WORDS = ("cuántos", "cuántas", "cuantos", "cuantas")


def is_count_question(task: str) -> bool:
    """¿Pide un conteo de registros (cuántos/cuántas) y no un valor (cuánto cuesta...)?"""
    low = task.lower()
    return any(w in low for w in _COUNT_WORDS)


def _clean_table(parsed) -> tuple[list[str], list[list[str]]]:
    if not isinstance(parsed, dict):
        return [], []
    cols = [str(c).strip() for c in (parsed.get("columnas") or [])]
    rows = []
    for r in parsed.get("filas") or []:
        if isinstance(r, (list, tuple)) and r:
            cells = [str(c).strip() for c in r]
            if cells[0]:
                rows.append(cells)
    return cols, rows


async def _ask_table(task: str, frame, prompt_name: str = "table") -> tuple[list[str], list[list[str]]]:
    """Transcribe la tabla visible (columnas, filas). Solo lectura: el filtrado se hace aparte."""
    prompt = load_prompt(prompt_name, task=task)
    res = await chat_vision(
        prompt,
        frame,
        TABLE_MODEL,
        downscale_to=None,
        json_mode=True,
        max_tokens=2500,
        provider={"sort": "latency"},
    )
    cols, rows = _clean_table(res.parsed)
    trace("table", filas=len(rows), cols=cols)
    return cols, rows


def _table_text(cols: list[str], rows: list[list[str]]) -> str:
    lines = [" | ".join(cols)] if cols else []
    lines += [" | ".join(r) for r in rows]
    return "\n".join(lines)


async def _select_ids(task: str, cols: list[str], rows: list[list[str]]) -> list[str]:
    """Modelo de texto: qué filas cumplen la pregunta. El conteo lo hace el código."""
    model = select(Capability.PLAN) or "deepseek/deepseek-v4-flash"
    prompt = load_prompt("rows_filter", task=task, table=_table_text(cols, rows))
    res = await chat_text(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        model,
        json_mode=True,
        max_tokens=2000,
    )
    return [str(i).strip() for i in ((res.parsed or {}).get("ids") or []) if str(i).strip()]


async def extract_count(task: str, frame, *, next_page=None, max_pages: int = 12, can_continue=lambda: True):
    """Cuenta registros: transcribe cada página (en paralelo con la paginación), filtra y cuenta en código.

    El fin del listado lo decide el código (`next_page` devuelve None si el botón falta, está
    deshabilitado o la pantalla no cambia). Si no se puede confirmar el final (límite o tiempo)
    devuelve None: un conteo parcial es un falso éxito.
    """
    tasks = [asyncio.create_task(_ask_table(task, frame))]
    complete = True
    pages = 1
    try:
        while next_page is not None:
            if pages >= max_pages or not can_continue():
                complete = False
                break
            new_frame = await next_page()
            if new_frame is None:
                break
            tasks.append(asyncio.create_task(_ask_table(task, new_frame)))
            pages += 1
        if not complete:
            return None
        results = await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    cols: list[str] = []
    rows: list[list[str]] = []
    seen = set()
    for c, rs in results:
        cols = cols or c
        for r in rs:
            key = tuple(r)
            if key not in seen:
                seen.add(key)
                rows.append(r)
    if not rows:
        return None
    valid = {r[0] for r in rows}
    ids = [i for i in dict.fromkeys(await _select_ids(task, cols, rows)) if i in valid]
    trace("count", paginas=pages, filas=len(rows), ids=len(ids))
    return str(len(ids))


async def extract_answer(task: str, frame, *, next_page=None, max_pages: int = 12, can_continue=lambda: True):
    """Extrae la respuesta de la pantalla: conteos por transcripción de tablas, el resto por lectura directa."""
    if is_count_question(task):
        return await extract_count(task, frame, next_page=next_page, max_pages=max_pages, can_continue=can_continue)
    page = await _ask_answer(task, frame)
    return page["respuesta"] if page else None


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
