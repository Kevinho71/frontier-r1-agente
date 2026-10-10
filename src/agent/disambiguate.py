"""Control de ambigüedad: ¿el listado filtrado contiene UN registro que encaje con la tarea?

Se transcribe la tabla visible (todas las columnas, paginando por código), un LLM de texto
propone los candidatos que encajan con lo que dice la tarea y el CÓDIGO decide:
más de uno ⇒ la tarea es ambigua y no se debe tocar nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from model import Capability, chat, load_prompt, select

from .summarize import _ask_table, _table_text
from .trace import trace


@dataclass
class Resolution:
    candidates: list[list[str]] = field(default_factory=list)  # filas completas
    cols: list[str] = field(default_factory=list)
    pages: int = 1
    complete: bool = True  # False si no se pudo recorrer todo el listado
    n_rows: int = 0  # filas transcritas en total

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1

    @property
    def unique(self):
        return self.candidates[0] if len(self.candidates) == 1 else None


async def _match_ids(task: str, cols, rows) -> list[str]:
    model = select(Capability.PLAN) or "deepseek/deepseek-v4-flash"
    prompt = load_prompt("match_rows", task=task, table=_table_text(cols, rows))
    res = await chat(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        model,
        json_mode=True,
        max_tokens=1000,
    )
    return [str(i).strip() for i in ((res.parsed or {}).get("ids") or []) if str(i).strip()]


def _merge(results):
    cols: list[str] = []
    rows: list[list[str]] = []
    seen = set()
    for c, rs in results:
        cols = cols or c
        for r in rs:
            if tuple(r) not in seen:
                seen.add(tuple(r))
                rows.append(r)
    return cols, rows


async def resolve_record(task: str, frame, *, next_page=None, max_pages: int = 6, can_continue=lambda: True) -> Resolution:
    """Candidatos del listado que encajan con la tarea (todas las páginas que se puedan recorrer)."""
    first = await _ask_table(task, frame, "table_full")
    if not first[1]:  # transcripción vacía: reintento único (un fallo del modelo no debe parecer "no existe")
        first = await _ask_table(task, frame, "table_full")
    results = [first]
    pages = 1
    complete = True
    while next_page is not None:
        if pages >= max_pages or not can_continue():
            complete = False
            break
        new_frame = await next_page()
        if new_frame is None:
            break
        results.append(await _ask_table(task, new_frame, "table_full"))
        pages += 1
    cols, rows = _merge(results)
    if not rows:
        return Resolution([], cols, pages, complete, 0)
    ids = list(dict.fromkeys(await _match_ids(task, cols, rows)))
    by_id = {r[0]: r for r in rows}
    cands = [by_id[i] for i in ids if i in by_id]
    trace("disambiguate", paginas=pages, filas=len(rows), candidatos=[c[0] for c in cands])
    return Resolution(cands, cols, pages, complete, len(rows))


def describe_row(cols, row) -> str:
    """'columna: valor' por celda, para nombrar a cada registro en el resumen."""
    if cols and len(cols) == len(row):
        return ", ".join(f"{c}: {v}" for c, v in zip(cols, row) if v)
    return " | ".join(row)


def ambiguity_reason(target: str, res: Resolution) -> str:
    items = "; ".join(f"({describe_row(res.cols, r)})" for r in res.candidates)
    return (
        f'Ambigüedad: {len(res.candidates)} registros coinciden con "{target}" y la tarea no indica cuál: '
        f"{items}. No se modificó nada; hace falta un dato que los distinga."
    )
