"""Spike 2: validar INPUT (mouse/teclado) por el puente. Clic en 'Comercial'."""

import asyncio
import os
import time

from PIL import Image

from bridge_test import make_opener, HOST, PASSWORD, OUT_DIR

import asyncvnc


async def shot(client, name):
    img = await client.screenshot()
    path = os.path.join(OUT_DIR, name)
    Image.fromarray(img).save(path)
    print(f"[shot] {name}")
    return img


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with asyncvnc.connect(HOST, 5900, password=PASSWORD, opener=make_opener()) as client:
        print(f"[vnc] conectado {client.video.width}x{client.video.height}")
        await shot(client, "input_00_home.png")

        # Clic en el menu "Comercial" (~x=110, y=47)
        client.mouse.move(110, 47)
        await client.drain()
        client.mouse.click()
        await client.drain()
        print("[vnc] clic en Comercial enviado")
        await asyncio.sleep(1.2)
        await shot(client, "input_01_comercial_open.png")

        # Cerrar el menu
        client.keyboard.press("Escape")
        await client.drain()
        await asyncio.sleep(0.5)
        await shot(client, "input_02_after_escape.png")
        print("[vnc] fin")


if __name__ == "__main__":
    asyncio.run(main())
