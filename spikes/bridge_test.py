"""
Spike: validar el puente WebSocket(websockify) <-> asyncvnc (RFB).

Objetivo: comprobar que podemos hablar el protocolo VNC a traves del
unico endpoint expuesto (wss://<host>/websockify) y capturar un framebuffer.

NO es el diseno final: solo decide camino A (VNC directo por puente) vs B (Playwright).
"""

import asyncio
import os
import sys
import time

import asyncvnc
import websockets

HOST = os.environ.get("DESKTOP_HOST", "frontier-r1-tn06-production.up.railway.app")
PASSWORD = os.environ.get("DESKTOP_PASS", "0e6cf456")
OUT_DIR = os.path.join(os.path.dirname(__file__), "captures")


class WebSocketWriter:
    """Adapta un WebSocket a la interfaz StreamWriter que asyncvnc espera.

    write() es sincrono y encola; un task en background envia en orden.
    drain() espera a que la cola se vacie (equivale a 'flush').
    """

    def __init__(self, ws):
        self._ws = ws
        self._q = asyncio.Queue()
        self._closed = False
        self._task = asyncio.create_task(self._sender())

    def write(self, data):
        self._q.put_nowait(bytes(data))

    async def _sender(self):
        try:
            while True:
                data = await self._q.get()
                if data is None:
                    self._q.task_done()
                    break
                await self._ws.send(data)
                self._q.task_done()
        except Exception as e:  # noqa: BLE001
            print(f"[sender] termina: {e!r}", file=sys.stderr)

    async def drain(self):
        await self._q.join()

    def close(self):
        if not self._closed:
            self._closed = True
            self._q.put_nowait(None)

    async def wait_closed(self):
        try:
            await asyncio.shield(self._task)
        except Exception:
            pass
        try:
            await self._ws.close()
        except Exception:
            pass

    def is_closing(self):
        return self._closed


async def _pump(ws, reader):
    """Alimenta el StreamReader con los frames binarios del WebSocket."""
    try:
        async for msg in ws:
            data = msg if isinstance(msg, (bytes, bytearray)) else msg.encode()
            reader.feed_data(bytes(data))
    except Exception as e:  # noqa: BLE001
        print(f"[pump] termina: {e!r}", file=sys.stderr)
    finally:
        reader.feed_eof()


def make_opener():
    async def opener(host, port):
        url = f"wss://{host}/websockify"
        print(f"[bridge] conectando {url} (subprotocolo 'binary')...")
        ws = await websockets.connect(
            url,
            subprotocols=["binary"],
            max_size=None,
            ping_interval=None,
            open_timeout=10,
        )
        print(f"[bridge] websocket OK, subprotocolo negociado: {ws.subprotocol!r}")
        reader = asyncio.StreamReader()
        asyncio.create_task(_pump(ws, reader))
        return reader, WebSocketWriter(ws)

    return opener


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    opener = make_opener()

    t0 = time.time()
    async with asyncvnc.connect(HOST, 5900, password=PASSWORD, opener=opener) as client:
        print(f"[vnc] handshake + auth OK en {time.time() - t0:.2f}s")
        print(f"[vnc] framebuffer: {client.video.width}x{client.video.height}")

        t1 = time.time()
        img = await client.screenshot()
        print(f"[vnc] screenshot OK en {time.time() - t1:.2f}s -> shape={img.shape} dtype={img.dtype}")

        from PIL import Image

        path = os.path.join(OUT_DIR, "bridge_capture.png")
        Image.fromarray(img).save(path)
        print(f"[vnc] guardado: {path}")

    print("[bridge] cerrado limpiamente")


if __name__ == "__main__":
    asyncio.run(main())
