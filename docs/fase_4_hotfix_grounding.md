# Fase 4 — Hotfix: grounding y verificación (corrección tras la prueba en vivo)

> Documento de decisiones y cambios tras la primera ejecución real del agente contra el
> escritorio de pruebas (tarea E3). Registra **qué se cambió, por qué, y la tabla de tradeoffs**.

## 1. Resumen

La prueba en vivo de E3 (`¿Cuántas facturas vencidas tiene Ferretería Ruiz?`) expuso que el
*plumbing* del agente conectaba y corría, pero **no navegaba**: devolvía `respuesta: 0` cuando la
esperada es `45`, y terminaba en la pantalla de inicio. Se diagnosticaron **cuatro causas raíz** y
se corrigieron en `model/` y `agent/`. **Ninguna de las 5 pruebas oficiales pasa todavía**: el
bloqueante restante es la **precisión del grounding** (coordenadas de clic), una limitación de los
modelos de visión disponibles, no del loop.

## 2. Causas raíz (con evidencia en vivo)

| # | Causa | Evidencia | Severidad |
|---|---|---|---|
| 1 | `ground.txt` era demasiado permisivo con `done` | `ui-tars`/`qwen` respondían `{"actions":[], "done":true}` sin hacer nada | Bloqueante |
| 2 | `loop.py` confiaba en `act_res.done` para terminar | Un `done:true` falso en el 1er hito cortaba toda la tarea | Bloqueante |
| 3 | `ling-3.0-flash-vl` devuelve **vacío** con `json_object` | `ling json_mode=True → ''` vs `json_mode=False → texto` | Bloqueante (CHECK roto) |
| 4 | Los modelos devuelven **píxeles absolutos** en vez de 0–1 | `ui-tars → {"x":129,"y":29}` (píxeles) y `qwen → x:156` o `x:0.15` mezclados | Alto |

## 3. Qué cambió

| Archivo | Antes | Después |
|---|---|---|
| `model/prompts/ground.txt` | Permitía `done:true` con acciones vacías; pedía coords 0–1 | Obliga ≥1 acción de avance; pide píxeles absolutos (1280×800); sin campo `done` |
| `model/prompts/check.txt` | Veredicto sin criterio | `ok:true` **solo** si se ve el hito cumplido; si no, `ok:false` + descripción |
| `model/registry.py` | `CHECK = ling`, `GROUND = ui-tars` primero | `CHECK = qwen3-vl-30b (+235b)`; `GROUND = qwen3-vl-30b (+235b, ui-tars último)`; `ling` solo OCR |
| `agent/act.py` | devolvía `ActResult.done` (del modelo) y downscale 800 | Ya no hay `done`; grounding a **resolución completa** (sin ambigüedad de escala) |
| `agent/loop.py` | rompía por `act_res.done`; un solo `done` global | La compleción la decide **solo `check()`**; recorre todos los hitos; `task_done` global |
| `agent/actions.py` | `normalize_coords` asumía 0–1 | **Auto-detecta** fracción (`[-1.5,1.5]`) vs píxel absoluto, luego clamp |
| `agent/plan.py` | devolvía `[]` ante flakiness | Reintenta 1× antes de ceder al fallback `[task]` |
| `model/client.py` | `parsed=None` con `json_mode` se silenciaba | Si `json_mode` y no hay JSON válido → error **retryable** (no silenciar) |
| `tests/` | 22 tests | 25 tests (nuevos: registry CHECK/GROUND, coords absolutas, clamp) |

## 4. Por qué (detalle)

1. **Quitar `done` del grounding.** El modelo de grounding no debe juzgar si el hito está completo
   (lo hace mal); solo propone acciones. La responsabilidad de "¿se cumplió?" pasa a `check()`,
   que ve la pantalla resultante. Esto elimina la fuente del falso `terminada`.

2. **CHECK con `qwen3-vl-30b` en vez de `ling`.** `ling` es barato pero no soporta
   `response_format=json_object` (devuelve string vacío). `qwen` sí devuelve JSON estructurado y
   su veredicto fue correcto en la prueba (`ok:false` al abrir el menú equivocado). `ling` queda
   solo para OCR (transcripción libre, `json_mode=False`).

3. **Grounding a resolución completa + coords tolerantes.** Los modelos ignoran la instrucción
   "0–1" y devuelven píxeles (a veces una mezcla). Enviar la imagen **sin downscale** elimina la
   ambigüedad de escala y `normalize_coords` auto-detecta el convenio. Esto es más robusto que
   insistir en un solo formato.

4. **`check()` como única fuente de verdad de avance.** Antes el loop cortaba al primer `done`
   (correcto o no). Ahora cada hito se intenta hasta `check().ok` (o agotar intentos), y el
   `estado` final es `terminada` solo si **todos** los hitos se verificaron (o, en preguntas, si se
   extrajo la respuesta).

## 5. Tabla de tradeoffs

| Decisión | Elegido | Alternativa descartada | Por qué |
|---|---|---|---|
| Modelo de CHECK | `qwen3-vl-30b-a3b-instruct` ($0.15/$0.60) | `ling-3.0-flash-vl` ($0.021) | `ling` no produce JSON; fiabilidad > costo (~$0.01/tarea) |
| Modelo de GROUND (primario) | `qwen3-vl-30b` | `bytedance/ui-tars-1.5-7b` | `ui-tars` devuelve píxeles y apunta al menú equivocado |
| Contrato de GROUND | solo `actions` (sin `done`) | `actions` + `done` | `done` del modelo era el origen del falso éxito |
| Coordenadas | píxeles absolutos + auto-detect | normalizadas 0–1 estrictas | los modelos no cumplen "0–1"; auto-detect tolera ambos |
| Resolución de grounding | completa (1280×800) | downscale 800 | sin re-escalado no hay ambigüedad de coords; costo extra menor |
| Verificación de avance | `check()` (visión) | `act().done` | `check` ve la pantalla real; `done` es auto-reportado y no fiable |
| Respuesta vacía con `json_mode` | error retryable | silenciar `parsed=None` | fallar fuerte evita avanzar con datos nulos |
| Plan vacío | reintentar 1× | fallback directo `[task]` | el flake del modelo de texto se recupera sin degradar el plan |

## 6. Estado de las pruebas oficiales

| Prueba | Estado | Resultado |
|---|---|---|
| E1 (crear cliente) | ⬜ no intentada | — |
| E2 (corregir dirección) | ⬜ no intentada | — |
| E3 (pregunta → `45`) | ❌ **falla** | `respuesta: 0` (esperado `45`); el agente no navega |
| E4 (exportar septiembre) | ⬜ no intentada | — |
| E5 (ambigua → `fallida`) | ⬜ no intentada | — |

## 7. Limitación pendiente (bloqueante): precisión del grounding

Tras los fixes, el loop ya no se detiene en falso y `check()` verifica correctamente. Pero el
**grounding de coordenadas sigue impreciso**: al pedir "localiza el menú *Cartera*", los modelos
devuelven `x≈157`, que en la app es el menú **"Comercial"** (verificado: clicar 157 abre
"Comercial → Maestros/Ventas"). Incluso con *feedback* explícito ("Cartera está a la derecha de
Comercial") el modelo insiste en `x≈157`, y hacer zoom a la barra de menú lo empeora (`x=71`).
Es decir, **no hay un modelo disponible que ubique texto con precisión de píxel** de forma fiable.

### Opciones para resolverlo (siguiente iteración)

| Opción | Qué | Riesgo |
|---|---|---|
| **A. Buscar y verificar** | Clic → OCR del dropdown → si no es el menú esperado, clic adyacente (corrección en bucle) | Latencia (más pasos); pero usa señales baratas y fiables (OCR) |
| **B. OCR con bounding boxes** | Modelo que devuelva texto + posición exacta (grounding OCR) | ¿Existe en OpenRouter? A verificar |
| **C. Modelo denso más fuerte** | `qwen3-vl-235b` denso (no MoE) o similar | Costo/latencia; puede reventar los 5 min |
| **D. Navegación por teclado** | Alt+letra / flechas si el menú lo soporta | Depende de la app (no garantizado) |

**Recomendación:** A (búsqueda + verificación con OCR) — convierte "coordenada exacta" en "búsqueda
acotada con verificación barata", que es robusto y generalizable a la app de evaluación desconocida.

## 8. Validación del hotfix

- 25/25 tests unitarios OK (sin red), `py_compile` limpio.
- En vivo: `check()` ahora distingue "Comercial abierto ≠ Cartera" (`ok:false`, `changed:true`).
- En vivo: `plan()` devuelve hitos correctos; `qwen` devuelve JSON para CHECK/GROUND.
- Escritorio reseteado (`/__reset` 200) tras cada prueba.
