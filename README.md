# Reto 1 — El agente que opera lo que no tiene API

Agente de visión que opera un sistema legacy **sin API, sin documentación y sin DOM** — solo por píxeles sobre un escritorio remoto noVNC.

## Entregables

- **Design doc (1 página):** [`design/index.html`](design/index.html) — https://kevinho71.github.io/frontier-r1-agente/
- **Diagrama de arquitectura:** [`design/architecture.svg`](design/architecture.svg) / [`design/architecture.png`](design/architecture.png)

## Estructura

```
design/           # doc de diseño + diagrama
spikes/           # validación del puente WS↔RFB (asyncvnc) sobre el escritorio real
  bridge_test.py  # conecta wss://…/websockify, autentica, captura framebuffer
  input_test.py   # valida input (clic/teclado) por VNC
```

## Validado (spike)

- Transporte: `wss://<host>/websockify` con subprotocolo `binary` → `asyncvnc`.
- Framebuffer 1280×800, screenshot ~1s, coordenadas 1:1 con input VNC.
- Input: clic abre menús; los menús cierran con clic fuera (no con `Escape`).

## Stack

Python 3.12 · FastAPI · asyncio · asyncvnc + websockets · Pillow · OpenRouter (visión)
