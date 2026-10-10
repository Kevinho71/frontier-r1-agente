"""Conexion VNC a traves del puente WebSocket (websockify) → asyncvnc (RFB)."""

import asyncio
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse

import asyncvnc
import websockets


def normalize_url(raw_url: str) -> str:
    u = urlparse(raw_url)
    if u.scheme in ("http", "https"):
        u = u._replace(scheme="wss" if u.scheme == "https" else "ws")
    elif u.scheme not in ("wss", "ws"):
        raise ValueError(f"esquema no soportado: {u.scheme}")
    if u.path in ("", "/"):
        u = u._replace(path="/websockify")
    return urlunparse(u)


class _WebSocketWriter:
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
        except Exception as exc:
            print(f"[desktop:sender] {exc!r}", file=sys.stderr)

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
    try:
        async for msg in ws:
            data = msg if isinstance(msg, (bytes, bytearray)) else msg.encode()
            reader.feed_data(bytes(data))
    except Exception as exc:
        print(f"[desktop:pump] {exc!r}", file=sys.stderr)
    finally:
        reader.feed_eof()


def _make_opener(url: str):
    """Opener que se pasa a asyncvnc.connect para conectar por WebSocket."""

    async def opener(host, port):
        ws = await websockets.connect(
            url,
            subprotocols=["binary"],
            max_size=None,
            ping_interval=None,
            open_timeout=10,
        )
        reader = asyncio.StreamReader()
        asyncio.create_task(_pump(ws, reader))
        return reader, _WebSocketWriter(ws)

    return opener


@asynccontextmanager
async def connect(raw_url: str, password: str):
    """
    Conecta al escritorio remoto via VNC (async context manager).

    raw_url puede ser 'wss://host/websockify' (recomendado) o 'https://host'
    (se deriva a wss://host/websockify).

    Uso:
        async with connect(url, password) as client:
            frame = await screenshot(client)
            await click(client, x, y)
    """
    url = normalize_url(raw_url)
    host = urlparse(url).hostname or ""
    port = urlparse(url).port or 443
    opener = _make_opener(url)
    async with asyncvnc.connect(host, port, password=password, opener=opener) as client:

        async def reconnect():
            """Reabre la sesión VNC y reemplaza el estado del `client` en el sitio (las referencias
            que ya tiene el agente siguen siendo válidas). Se usa si el flujo RFB se desincroniza."""
            reader, writer = await opener(host, port)
            new = await asyncvnc.Client.create(reader, writer, None, password)
            try:
                client.writer.close()
            except Exception:
                pass
            client.__dict__.update(new.__dict__)

        client._reconnect = reconnect
        try:
            yield client
        finally:
            try:
                client.writer.close()  # tras una reconexión, el writer actual no es el que cierra asyncvnc
            except Exception:
                pass