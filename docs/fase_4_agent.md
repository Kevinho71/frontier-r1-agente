# Fase 4 — Síntesis: `src/agent/` (loop plan → act → check)

## 1. Resumen

Se construyó el loop del agente sobre píxeles: planifica la tarea en hitos, actúa por batches de
acciones con coordenadas normalizadas y verifica cada hito, devolviendo un `TaskResult` con estado
y resumen en el formato exacto de la evaluación (línea `respuesta: <valor>` con el número primero,
redacción de secretos).

| Archivo | Qué expone |
|---|---|
| `types.py` | `TaskResult` (estado, resumen, steps, cost_usd) |
| `redact.py` | `redact_text()`, `env_secrets()` (redactor de secretos) |
| `actions.py` | `execute_actions()`, `normalize_coords()`, `normalize_key()` |
| `plan.py` | `plan()` → OCR + modelo de texto → hitos |
| `act.py` | `act()` → GROUND (visión) → batch de acciones → ejecutar |
| `check.py` | `check()` → diff + OCR + veredicto por visión |
| `summarize.py` | `is_question()`, `extract_answer()`, `format_summary()` |
| `loop.py` | `run_task()` → orquestador con cortes |

Se añadió el prompt `model/prompts/answer.txt` (extracción de respuesta) y se reescribió
`plan.txt` para recibir texto OCR en lugar de captura.

## 2. Estado Anterior vs. Actual

| Aspecto | Antes | Ahora |
|---|---|---|
| `src/agent/` | No existía | Paquete completo con el loop híbrido |
| Loop de agente | Inexistente (solo primitivas de desktop/vision/model) | `run_task()` plan→act→check con timeout/pasos/estancamiento |
| Resumen final | Inexistente | `format_summary()` con `respuesta:` y redacción de secretos |
| Tareas de pregunta (E3) | Sin mecanismo | `is_question()` + `extract_answer()` (visión a resolución completa) |
| `plan.txt` | Recibía una captura adjunta (implicaba visión) | Recibe texto OCR (`{{context}}`), coherente con PLAN=texto |
| Prompts de model/ | plan/ground/check | + `answer.txt` |
| Cliente model | `chat(model=None)` enviaba `model: null` | Guard en `chat()`: sin modelo disponible → `LLMError` claro |

## 3. Decisiones Técnicas

1. **PLAN es texto (OCR + deepseek), no visión.** El registro de Fase 3 pone `PLAN =
   deepseek-v4-flash` (modelo de texto). La pantalla inicial se lee con OCR barato (`ling`) y el
   modelo de texto descompone la tarea en hitos sin coordenadas. El grounding real lo hace GROUND.
   Por eso `plan.txt` pasó de "captura adjunta" a "texto OCR" (`{{context}}`). Es más barato y la
   lectura del menú ya se validó exacta en Fase 2.

2. **GROUND sobre la captura completa downscaled (800px).** El grounding necesita ver la pantalla
   entera para ubicar el siguiente clic; se envía `downscale_to=800` (no crop de atención en v1) para
   balancear legibilidad y tokens. Las coordenadas devueltas son 0–1 y se convierten a píxeles con la
   forma real del framebuffer (`normalize_coords`, clampado al viewport).

3. **CHECK en cascada: diff → OCR → LLM.** El diff (`changed`) es la señal barata de "¿cambió la
   pantalla?"; el OCR aporta el texto visible como contexto; el veredicto `{ok, description}` lo da el
   modelo de visión. En v1 el OCR no corta el circuito (se usa como contexto para fiabilidad, no para
   decidir), y el estancamiento se maneja en el loop con `frame_signature`.

4. **Las preguntas se resuelven por extracción, no por cambio de UI.** `is_question()` detecta el tipo
   por heurística (`?` o "cuánt…/cuál…"). Al final del loop, si es pregunta, `extract_answer()` lee la
   última pantalla a resolución completa (`downscale_to=None`, para no perder números chicos) y el
   resultado determina `terminada`/`fallida`, anulando el criterio de "cambio de UI".

5. **Redactor de secretos en `agent/redact.py`.** El resumen y los errores pasan por `redact_text()`,
   que reemplaza la contraseña del escritorio y los valores de `OPENROUTER_API_KEY`/`TEAM_TOKEN` por
   `<REDACTED>` (omite strings <4 chars para no sobreredactar). En Fase 6 se consolidará con `logs/writer.py`.

6. **Cortes defensivos.** `timeout_s=300` con `reserve_s=30` (para el resumen), `max_steps=25`,
   `MAX_ATTEMPTS_PER_MILESTONE=4`, y estancamiento tras 3 pantallas con el mismo `frame_signature`.
   La conexión VNC siempre se cierra (context manager), cumpliendo "detén el trabajo al reportar".

7. **Normalización de teclas.** `normalize_key` traduce alias (`Enter`→`Return`, `Esc`→`Escape`) a los
   keysyms que espera asyncvnc, porque el GROUND puede emitir nombres no canónicos.

## Validación

- 22 tests unitarios (11 de model + 11 de agent) en `tests/`, **22/22 OK** (sin red).
- Import de `agent` completo y `py_compile` de todos los módulos sin errores.
- `is_question` clasifica E1 (acción) vs E3 (pregunta) correctamente.
- `format_summary` emite `respuesta: 45` y redacta la contraseña.

## Pendiente (integración, Fases 5–6)

- End-to-end contra el escritorio real (E1–E5): afinar prompts y heurísticas, en particular la
  detección de homónimos de E5 (claves `52345678` / `1019876543`) que hoy depende de la calidad del
  grounding/check por visión.
- `logs/` (JSONL + artefactos) consumirá `agent.redact` y el `TaskResult.cost_usd`.
