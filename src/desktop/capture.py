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