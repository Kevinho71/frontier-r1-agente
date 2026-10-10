# Fase 3 — Síntesis: `src/model/` (routing + cliente OpenRouter + prompts)

## 1. Resumen

Se construyó la capa de modelos: routing por capacidad, cliente OpenRouter con retry/backoff,
manejo de cuota (429) y estimación de costo, y las plantillas de prompt para PLAN, GROUND y CHECK.

| Archivo | Qué expone |
|---|---|
| `registry.py` | `Capability` (PLAN/GROUND/CHECK/HARD), `CANDIDATES` (catálogo por capacidad), `PRICES`, `price_for()` |
| `router.py` | `select()`, `mark_exhausted()`, `is_exhausted()`, `reset()` |
| `client.py` | `chat()`, `chat_vision()`, `LLMResult`, `LLMError`, parseo JSON defensivo, cost tracking |
| `prompts.py` | `load_prompt(name, **vars)` que lee `prompts/*.txt` |
| `prompts/{plan,ground,check}.txt` | plantillas: PLAN→hitos, GROUND→acciones con coords 0–1, CHECK→`{ok, description}` |

Además se unificó `src/vision/ocr.py`: `extract_text()` ahora delega en `model.client.chat_vision`
en lugar de su httpx ad hoc. Validado con 11 tests unitarios (sin red) y verificación de imports.

## 2. Estado Anterior vs. Actual

| Aspecto | Antes | Ahora |
|---|---|---|
| `src/model/` | No existía (greenfield) | Paquete completo: registry + router + client + prompts |
| Llamadas a OpenRouter | Solo `vision/ocr.py` hacía una llamada ad hoc (httpx directo, sin retry, sin routing, sin costo) | Un solo cliente `model.client` con retry/backoff+jitter, JSON defensivo, `usage`/`cost_usd` |
| Routing por capacidad | Inexistente (cada llamada hardcodeaba un modelo) | `select(Capability)` con candidatos ordenados + fallback, y `mark_exhausted` ante 429/404 |
| Agotamiento de cuota | No se manejaba (un 429 crasheaba o colgaba) | 429 `retryable:false` / 404 → modelo marcado `exhausted` y excluido del routing |
| Salida estructurada | Ninguna (texto crudo) | `response_format=json_object` + parseo defensivo del primer bloque `{...}` |
| `vision/ocr.py` | Importaba `httpx`, `os`, `to_data_url` y armaba su propio payload | Delega en `model.client.chat_vision`; mantiene firma pública (`frame, model, prompt → str`) |

## 3. Decisiones Técnicas

1. **`Capability` vive en `registry.py`, no en `router.py`** (desvío del plan original).
   El plan ponía el enum en `router.py`, pero `registry` necesita el enum como clave de
   `CANDIDATES` y `router` necesita los candidatos del registry: meter el enum en `router`
   crearía un import circular. Se colocó en `registry` (módulo sin dependencias) y `router` lo
   re-exporta. Resultado: dependencias en un solo sentido `registry ← router ← client`.

2. **Cliente con `httpx`, no SDK de OpenAI.** El repo ya usa `httpx` (en el OCR anterior) y no
   hay SDK instalado; un cliente propio deja el control del retry/agotamiento/costo sin una
   dependencia nueva.

3. **`json_object` + parseo defensivo, no `json_schema`.** `json_object` tiene soporte amplio en
   los proveedores de OpenRouter; el parseo defensivo (extraer el primer bloque `{...}` balanceado)
   es respaldo por si el modelo devuelve texto con relleno. Los prompts incluyen la palabra "JSON"
   (requisito de OpenRouter para `json_object`).

4. **429/404 marcan el modelo `exhausted`, 5xx/timeout reintentan.** Regla aprendida en la práctica
   (documentada en `RETO1_CONTEXTO.md` §7): la cuota agotada no es reintentable. Se distingue vía
   `error.metadata.retryable` de OpenRouter. El agotamiento es un set en memoria; el contenedor es
   persistente, así que equivale a "el resto del día".

5. **Costo estimado, no facturado.** `cost_usd` se calcula de tokens × precios por millón. OpenRouter
   factura imágenes distinto, así que el costo de visión es aproximado; sirve para el presupuesto de
   los 5 min y el `TaskResult.cost_usd` de Fase 4, no como métrica exacta.

6. **Placeholders de prompt con doble llave `{{var}}`.** Los prompts muestran ejemplos JSON con
   llaves `{}`; usar `.format()` los rompería. `load_prompt` hace un reemplazo literal solo de las
   llaves `{{var}}` conocidas, dejando intacto el JSON de ejemplo.

7. **Catálogo como defaults, no como verdad.** Los IDs/precios del plan y del design doc eran
   inconsistentes entre sí (ej. HARD: `qwen3-vl-30b` vs `qwen3-vl-235b`; PLAN: `deepseek-v4-flash` vs
   `deepseek-v4.1-flash`). Se consolidó una sola fuente (`registry.py`) con los candidatos y fallbacks,
   y se dejó `spikes/model_test.py` para verificarlos contra el catálogo vivo antes de la evaluación.

## Validación

- 11 tests unitarios `tests/test_model.py` (stdlib `unittest`): routing, fallback, agotamiento,
  `exclude`, parseo JSON (puro / con relleno / nulo), estimación de costo, backoff creciente. **11/11 OK.**
- Import de `model`, `vision` y `vision.ocr` sin errores (sin import circular).
- `load_prompt` con las 3 plantillas devuelve contenido no vacío.
- `spikes/model_test.py` (smoke en vivo) compila; requiere `OPENROUTER_API_KEY` para correr.
