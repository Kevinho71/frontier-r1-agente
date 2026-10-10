"""Captura de pantalla y recorte."""

import asyncio

import asyncvnc
import numpy as np


async def screenshot(client: asyncvnc.Client) -> np.ndarray:
    """Captura el framebuffer completo como array RGBA (h, w, 4).

    Si el flujo RFB se desincroniza (visto en vivo: ValueError con una codificación basura) o la
    conexión se corta, se reconecta una vez y se reintenta en vez de perder la tarea entera.
    """
    try:
        return await client.screenshot()
    except (ValueError, asyncio.IncompleteReadError, ConnectionError, OSError):
        reconnect = getattr(client, "_reconnect", None)
        if reconnect is None:
            raise
        await reconnect()
        await asyncio.sleep(1.0)
        return await client.screenshot()


async def wait_and_capture(
    client: asyncvnc.Client, delay_s: float = 1.2
) -> np.ndarray:
    """Espera a que la pantalla se repinte y captura."""
    await asyncio.sleep(delay_s)
    return await screenshot(client)