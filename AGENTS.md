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
- ✅ **Fase 4** `src/agent/` — loop plan→act(batch)→check + resumen con formato exacto y redacción.
- ✅ **Iteración 3** (planificación + estado entre pasos + lectura de tablas): **E3 pasa (45)**. Ver `docs/fase_4_hotfix_grounding.md`.
- ✅ **Iteración 4**: control de ambigüedad (E5), guard anti-duplicado (E1), prompts genéricos. **E1–E5 pasan `/__check`** (1 corrida cada una; falta medir varianza).
- ✅ **Fase 5/6** `src/api/` (FastAPI, store en memoria, workers asyncio) + `src/logs/` (JSONL por tarea redactado). **Dockerfile** probado localmente.
- ⬜ **Fase 7 deploy**: subir la imagen a Railway/Fly (requiere cuenta) y verificar `/health` + una tarea.

**Plan maestro:** `docs/plan_implementacion.md` (contiene credenciales → NO commitear).
**Síntesis por fase:** `docs/fase_1_desktop.md`, `docs/fase_2_vision.md`, `docs/fase_3_model.md`, `docs/fase_4_agent.md`, `docs/fase_4_hotfix_grounding.md`.
**Próximo paso (traspaso):** `docs/proximo_paso.md` — qué falla ahora (E5 y E1/E2/E4) y qué hacer.

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
src/vision/    percepción barata: crop_region, downscale, changed, diff_fraction, extract_text, detect_elements
src/model/     router por capacidad (registry+router) + cliente OpenRouter (client) + prompts
src/agent/     loop híbrido plan→act(batch)→check, con resumen formato exacto
src/api/       FastAPI: /health, POST /tasks (<2s), GET /tasks/{id}; src/logs/ JSONL por tarea (DATA_DIR)
```

## Decisiones de diseño clave (no deshacer sin razón)

- **`asyncvnc` + puente WebSocket** sobre Playwright: menos capas, framebuffer exacto, coords 1:1.
- **Agente híbrido** con batching por pantalla (una llamada por cambio de pantalla, no por clic).
- **Coords normalizadas 0–1** (robustas a cambio de resolución).
- **`click` mantiene ≥150ms** porque el servidor ignora clics <100ms.
- **`wait_and_capture` espera ≥1s** porque el repintado tarda hasta 1s.
- **Umbral de diff 0.1%** (`changed`) porque un dropdown cambia ~0.25% pero el "sin cambio" da 0.0.
- **`check()` decide el avance, no el grounding** (el `done` auto-reportado del modelo era falso; ver `docs/fase_4_hotfix_grounding.md`).
- **CHECK/GROUND con `qwen3-vl-30b`** (`ling` no soporta `json_object`; `ui-tars` devuelve coords en píxeles y apunta mal).
- **Grounding por detección (detect + select):** `vision/locate.py` detecta elementos con bounding boxes y `click_text` clica el centro de la caja; nunca se adivina una coordenada. Detector `qwen3-vl-235b` (validado: 30b da boxes mal).
- **Cajas de Qwen3-VL = escala 0–1000** (`scale_for`). Verificado contra la pantalla real; no tratarlas como píxeles.
- **Plan por entidad objetivo** (genérico, sin nombres de la app): navegar al listado de la entidad; cliente/estado/fechas son filtros dentro de él. Cada hito lleva `pantalla_esperada` que usa `check`.
- **`act()` con memoria** (`ActState`, `history`, `feedback`) y detección **en paralelo** con el `check` (`prefetched`).
- **Conteos**: transcribir tabla (235b) + paginar por código + filtrar ids con LLM de texto + contar en código. Nunca confiar en que el VLM cuente ni en su `hay_mas_paginas`.
- **Ambigüedad genérica:** el plan marca el hito de localizar (`localiza_registro`); `agent/disambiguate.py` transcribe el listado (todas las columnas), un LLM de texto propone candidatos y el CÓDIGO decide (>1 ⇒ `fallida` nombrando cada fila). Falla cerrada: si no se puede verificar, no se toca nada.
- **Guard anti-duplicado:** `ActState.committed` bloquea volver a pulsar el mismo botón de confirmación (Guardar/Crear/Exportar…) salvo error de validación.
- **Costo:** `model.client.cost_acc` (contextvar) acumula TODAS las llamadas de la tarea.
- **Prompts genéricos:** nada de nombres de la app (la de evaluación es otra). Los datos de prueba solo viven en `tests/` y `spikes/`.
- **Contenedor persistente** (Fly.io/Railway), no Lambda (el WS VNC vive 5 min; cold-start come presupuesto).

## Cómo verificar

- Contra el escritorio: conectar, capturar, OCR, diffs (ver scripts en `spikes/`).
- Oráculo dev: `POST /__reset` y `POST /__check` (endpoints del escritorio, Bearer con token).
- Pruebas oficiales E1–E5 en `frontier-reto-1/pruebas/` (gitignored, son material).
- Tests de `model/`: `PYTHONPATH=src python -m unittest tests.test_model -v` (sin red).
- Tests: `PYTHONPATH=src python -m unittest tests.test_model tests.test_agent tests.test_api -v` (sin red). Traza en vivo: `RETO1_TRACE=1`; frames por paso: `RETO1_DUMP=<dir>`.
- Verificar IDs del catálogo contra OpenRouter (necesita `OPENROUTER_API_KEY`): `PYTHONPATH=src python spikes/model_test.py`.

## Reglas de commit

- Commits con prefijo (`feat(desktop):`, `fix`, `docs:`, `ci:`).
- No committear: `.env`, `RETO1_CONTEXTO.md`, `docs/plan_implementacion.md`, `frontier-reto-1/`, venvs.
- El doc público de diseño vive en `design/` (servido por GitHub Pages); evita tocar su HTML salvo que se pida.