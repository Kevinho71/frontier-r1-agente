"""Paginación: localiza el control "siguiente" y avanza páginas para leer listados largos."""

from __future__ import annotations

from desktop.capture import wait_and_capture
from desktop.input import click
from vision.diff import changed as frame_changed
from vision.locate import detect_elements

from .actions import normalize_text
from .trace import trace

_NEXT_LABELS = ("siguiente", "next", "proxima", "pagina siguiente", "adelante")
_PREV_LABELS = ("anterior", "previous", "prev", "pagina anterior", "atras")


def find_next_control(elements):
    """Elemento "siguiente página" por etiqueta (sin acentos/puntuación); None si no hay."""
    for el in elements or []:
        t = normalize_text(el.text)
        if t and any(t == lab or t.startswith(lab) for lab in _NEXT_LABELS):
            return el
    return None


def find_prev_control(elements):
    """Elemento "página anterior" por etiqueta; None si no hay."""
    for el in elements or []:
        t = normalize_text(el.text)
        if t and any(t == lab or t.startswith(lab) for lab in _PREV_LABELS):
            return el
    return None


class Pager:
    """Avanza páginas sobre la pantalla actual. Detecta el control una sola vez."""

    def __init__(self, client, frame, detect_task=None):
        self.detect_task = detect_task  # detección ya lanzada sobre `frame` (reutilizable)
        self.client = client
        self.frame = frame
        self.el = None
        self.looked = False
        self.cost = 0.0
        self.moved = 0

    async def back(self):
        """Vuelve a la primera página (deshace los `next`). La posición del control cambia con
        el largo de la tabla, así que se detecta sobre la pantalla actual en cada paso."""
        while self.moved > 0:
            try:
                els, c = await detect_elements(self.frame)
                self.cost += c
            except Exception:
                return self.frame
            el = find_prev_control(els)
            if el is None:
                return self.frame
            await click(self.client, el.x, el.y)
            self.frame = await wait_and_capture(self.client)
            self.moved -= 1
        return self.frame

    async def next(self):
        if not self.looked:
            self.looked = True
            try:
                if self.detect_task is not None:
                    els, _ = await self.detect_task  # su costo ya se contó en el loop
                else:
                    els, c = await detect_elements(self.frame)
                    self.cost += c
                self.el = find_next_control(els)
            except Exception:
                self.el = None
            trace("pager.control", el=self.el)
        if self.el is None:
            return None
        await click(self.client, self.el.x, self.el.y)
        new = await wait_and_capture(self.client)
        if not frame_changed(self.frame, new):
            trace("pager.fin")
            return None  # botón deshabilitado o último listado: la pantalla no cambió
        self.frame = new
        self.moved += 1
        return self.frame
