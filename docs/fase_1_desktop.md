# Fase 1 — Síntesis: `src/desktop/` (I/O VNC)

## 1. Resumen

Se construyó la capa de entrada/salida hacia el escritorio remoto, refactorizando los spikes
(`spikes/bridge_test.py`, `spikes/input_test.py`) en un módulo limpio y reutilizable:

| Archivo | Qué expone |
|---|---|
| `connection.py` | `normalize_url()`, `connect()` (async context manager) |
| `capture.py` | `screenshot()`, `wait_and_capture()` |
| `input.py` | `click()`, `press_key()`, `select_all()`, `type_text()`, `wait_ms()` |

## 2. Estado Anterior vs. Actual

- **Antes:** código de prueba ad-hoc en `spikes/` que construía la URL a mano y usaba
  `async with asyncvnc.connect(...)` directamente.
- **Ahora:** API pública en `src/desktop/`:
  - `connect(url, password)` es **async context manager** (garantiza cierre limpio al salir).
  - `normalize_url()` normaliza cualquier URL de entrada.
  - `click()` encapsula el timing de pulsación.

## 3. Decisiones Técnicas

1. **`asyncvnc` + puente WebSocket, no Playwright.**
   El escritorio solo expone `wss://…/websockify` (el puerto 5900 no está abierto, verificado
   por escaneo). Hablamos RFB dentro de un WebSocket con subprotocolo `binary`, presentándole a
   `asyncvnc` un stream propio. Motivo: **framebuffer exacto, coordenadas 1:1, sin Chromium**;
   cada capa menos es un punto de falla menos.

2. **`click()` mantiene el botón ≥150ms.**
   El material observa que el servidor **ignora clics <100ms** entre bajar y soltar, y
   `asyncvnc.click()` envía press+release back-to-back (sin delay). Por eso el clic se emite
   manualmente: press → drain → sleep(150ms) → release → drain.

3. **`wait_and_capture()` espera ≥1s antes de capturar.**
   "Después de un clic, la pantalla tarda hasta 1 segundo en repintar; una captura inmediata
   trae la pantalla vieja". El wait es obligatorio para no operar sobre una imagen stale.

4. **`connect()` como context manager.**
   La conexión VNC debe cerrarse al terminar la tarea; si el agente deja el socket abierto, la
   evaluación sigue contando "acciones fuera de la tarea" en la tarea siguiente.

5. **`normalize_url()` defensivo.**
   El contrato dice que `escritorio.url` llega como `wss://…/websockify`, pero por si la eval
   manda `https://host` (la página), se deriva a `wss://host/websockify`; si ya trae un
   sub-path, se respeta.

## Validación

- Conexión → framebuffer **1280×800**.
- `screenshot` y `wait_and_capture` correctos.
- `click` sobre "Comercial" envía el evento correctamente.
- `normalize_url` cubre: `wss://host/websockify`, `https://host`, `wss://host`,
  `http://host`, y `wss://host/sub-path`.
- Escritorio reseteado con `/__reset` tras las pruebas.
