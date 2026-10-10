# AGENTS.md — contexto de proyecto para agentes

## Qué es esto

**Reto 1 — "El agente que opera lo que no tiene API".** Construimos un servicio HTTP asíncrono
(Python) que, ante una tarea en lenguaje natural, se conecta a un **escritorio remoto por VNC**
y lo opera **solo con píxeles** (prohibido el DOM), como lo haría un empleado nuevo.

## Puntos que SÍEMPRE debes respetar

1. **Solo píxeles.** Nunca leer el DOM ni abrir la URL de la app objetivo. El canal es VNC (`wss://.../websockify`).
2. **Sin proveedores externos de computer-use.** Solo LLM por API (OpenRouter).
3. **5 minutos por tarea.** El worker tiene timeout y reserva ~30s para el resumen.
4. **Secretos jamás en el repo.** Credenciales viven en `RETO1_CONTEXTO.md` y `.env` (gitignored).
   Cualquier log/resumen pasa por un redactor de secretos.

## Estado actual

- ✅ **Fase 1** `src/desktop/` — conexión VNC + input (click ≥100ms) + capture con wait.
- ✅ **Fase 2** `src/vision/` — crop/downscale, diff por hash/píxeles, OCR barato.
- ✅ **Fase 3** `src/model/` — router por capacidad + cliente OpenRouter (retry/429→agotado) + prompts.
- ⬜ Fase 4 `agent/`, Fase 5 `api/store/queue`, Fase 6 `logs/`, Fase 7 deploy.

**Plan maestro:** `docs/plan_implementacion.md` (contiene credenciales → NO commitear).
**Síntesis por fase:** `docs/fase_1_desktop.md`, `docs/fase_2_vision.md`, `docs/fase_3_model.md`.

## Entorno (cómo correr)

```bash
cd /home/kevin/RETO1FRONTIER
source .venv/bin/activate          # venv creado con `uv` (no hay pip de sistema)
PYTHONPATH=src python ...          # el código vive en src/
```

- Dependencias: `asyncvnc websockets pillow httpx numpy` (+ `fastapi uvicorn` en Fase 5).
- Instalar: `uv pip install <pkg>`.
- Variables: `OPENROUTER_API_KEY` (obligatoria para visión/OCR), `TEAM_TOKEN` (Fase 5).

## Estructura y responsabilidades

```
src/desktop/   I/O: connect(url,pwd) [context manager], screenshot, click, type, select_all
src/vision/    percepción barata: crop_region, downscale, changed, diff_fraction, extract_text
src/model/     router por capacidad (registry+router) + cliente OpenRouter (client) + prompts
src/agent/     (F4) loop híbrido plan→act(batch)→check, con resumen formato exacto
src/api/       (F5) FastAPI: /health, POST /tasks (<2s), GET /tasks/{id}
```

## Decisiones de diseño clave (no deshacer sin razón)

- **`asyncvnc` + puente WebSocket** sobre Playwright: menos capas, framebuffer exacto, coords 1:1.
- **Agente híbrido** con batching por pantalla (una llamada por cambio de pantalla, no por clic).
- **Coords normalizadas 0–1** (robustas a cambio de resolución).
- **`click` mantiene ≥150ms** porque el servidor ignora clics <100ms.
- **`wait_and_capture` espera ≥1s** porque el repintado tarda hasta 1s.
- **Umbral de diff 0.1%** (`changed`) porque un dropdown cambia ~0.25% pero el "sin cambio" da 0.0.
- **Contenedor persistente** (Fly.io/Railway), no Lambda (el WS VNC vive 5 min; cold-start come presupuesto).

## Cómo verificar

- Contra el escritorio: conectar, capturar, OCR, diffs (ver scripts en `spikes/`).
- Oráculo dev: `POST /__reset` y `POST /__check` (endpoints del escritorio, Bearer con token).
- Pruebas oficiales E1–E5 en `frontier-reto-1/pruebas/` (gitignored, son material).
- Tests de `model/`: `PYTHONPATH=src python -m unittest tests.test_model -v` (sin red).
- Verificar IDs del catálogo contra OpenRouter (necesita `OPENROUTER_API_KEY`): `PYTHONPATH=src python spikes/model_test.py`.

## Reglas de commit

- Commits con prefijo (`feat(desktop):`, `fix`, `docs:`, `ci:`).
- No committear: `.env`, `RETO1_CONTEXTO.md`, `docs/plan_implementacion.md`, `frontier-reto-1/`, venvs.
- El doc público de diseño vive en `design/` (servido por GitHub Pages); evita tocar su HTML salvo que se pida.