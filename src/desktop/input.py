"""Input sobre el escritorio remoto: mouse y teclado con garantias de timing.

- click(): mantiene el boton ≥100ms para que el servidor no lo ignore.
- type_text(): tipeo caracter a caracter.
- select_all(): Ctrl+A para limpiar campo antes de escribir.
"""

import asyncio

import asyncvnc


async def click(
    client: asyncvnc.Client, x: int, y: int, button: int = 0, hold_ms: int = 150
):
    """Mueve el mouse a (x,y) y hace clic con ≥hold_ms de pulsacion."""
    client.mouse.move(x, y)
    await client.drain()

    mask = 1 << button
    client.mouse.buttons |= mask
    client.mouse._write()  # noqa: SLF001
    await client.drain()

    await asyncio.sleep(hold_ms / 1000)

    client.mouse.buttons &= ~mask
    client.mouse._write()  # noqa: SLF001
    await client.drain()


async def press_key(client: asyncvnc.Client, *keys: str):
    """Presiona y suelta una o varias teclas (ej: 'Enter', 'Escape')."""
    client.keyboard.press(*keys)
    await client.drain()


async def select_all(client: asyncvnc.Client):
    """Ctrl+A — selecciona todo el texto del campo con foco."""
    await press_key(client, "Control_L", "a")


async def type_text(client: asyncvnc.Client, text: str):
    """Tipea texto, caracter a caracter."""
    if text:
        client.keyboard.write(text)
        await client.drain()


async def wait_ms(ms: int):
    """Espera N milisegundos."""
    await asyncio.sleep(ms / 1000)