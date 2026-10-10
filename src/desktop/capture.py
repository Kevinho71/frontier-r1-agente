"""Captura de pantalla y recorte."""

import asyncio

import asyncvnc
import numpy as np


async def screenshot(client: asyncvnc.Client) -> np.ndarray:
    """Captura el framebuffer completo como array RGBA (h, w, 4)."""
    return await client.screenshot()


async def wait_and_capture(
    client: asyncvnc.Client, delay_s: float = 1.2
) -> np.ndarray:
    """Espera a que la pantalla se repinte y captura."""
    await asyncio.sleep(delay_s)
    return await client.screenshot()


def crop_region(
    frame: np.ndarray,
    x: int = 0,
    y: int = 0,
    width: int | None = None,
    height: int | None = None,
    margin: int = 0,
) -> np.ndarray:
    """
    Recorta una region del framebuffer, acotada a sus dimensiones.

    Si se pasa margin, la region se expande alrededor de (x,y) con ese margen
    (ignorando width/height). Util para ventana de atencion.
    """
    h, w = frame.shape[:2]
    if margin > 0:
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(w, x + margin)
        y2 = min(h, y + margin)
        return frame[y1:y2, x1:x2]

    x2 = min(w, x + width) if width is not None else w
    y2 = min(h, y + height) if height is not None else h
    return frame[y:y2, x:x2]