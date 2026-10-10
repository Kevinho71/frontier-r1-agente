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

---

# Iteración 2 — Grounding por detección ("detectar + seleccionar")

## 1. Resumen

Se reemplazó la **regresión de coordenadas** (el modelo adivina `x,y`) por **detección de elementos
con bounding boxes + selección por etiqueta** (método OmniParser). El clic sale del centro de la caja
detectada, no de una coordenada adivinada. Validado en vivo: `detect_elements` ubica "Cartera" en
`x≈211` (correcto) y el decisor elige `click_text "Cartera"`.

## 2. Por qué (retomando el diagnóstico)

Los modelos de visión **sí son fiables enumerando "qué hay y con qué caja"**, pero **no regresando un
punto exacto**. Evidencia en vivo (boxes de la barra de menú):

| Modelo | Box "Cartera" | ¿Correcto? |
|---|---|---|
| `qwen3-vl-30b-a3b` | `[140,48,178,70]` px → centro 159 | ❌ (159 es Comercial) |
| `qwen2.5-vl-72b` | `[0.14,0.02,0.18,0.06]` → centro 205 | ✅ (clic 205 abre Cartera→Facturas) |
| `qwen3-vl-235b` | `[0.14,0.02,0.18,0.06]` → centro 205 | ✅ |

Clicar el centro de la caja **correcta** abre el menú esperado. La posición la aporta el detector,
no el LLM que decide.

## 3. Qué cambió

| Archivo | Cambio |
|---|---|
| `model/prompts/detect.txt` | (nuevo) pedir elementos interactivos con box normalizada |
| `model/prompts/select.txt` | (nuevo) decidir acción por etiqueta sobre la lista de elementos |
| `vision/locate.py` | (nuevo) `detect_elements(frame) -> (Element[], cost)`; `_box_center` auto-detecta 0–1 vs px |
| `agent/actions.py` | `click_text` + `find_element` (fuzzy: sin acentos/espacios) + `normalize_text` |
| `agent/act.py` | detecta → decide (texto barato) → ejecuta; fallback a grounding por visión si no detecta |
| `tests/` | +6 tests (normalize_text, find_element, box_center) → **31 tests** |

## 4. Tradeoffs

| Decisión | Elegido | Alternativa | Por qué |
|---|---|---|---|
| Detector | `qwen3-vl-235b-a22b` (VLM vía API) | OCR local (tesseract/easyocr) | cumple "solo LLM por API", sin dep de sistema; boxes correctas |
| Decisión | texto (`deepseek`) sobre la lista de etiquetas | visión (`qwen`) otra vez | decidir por etiqueta es barato y suficiente |
| Coordenadas | auto-detect 0–1 / px en `_box_center` | un solo convenio | los modelos mezclan ambos formatos |
| Match de etiqueta | fuzzy (sin acentos, substring) | exacto | OCR/VLM varía acentos ("Papelería" vs "papeleria") |

## 5. Resultado E3 (tras esta iteración)

- **Grounding resuelto:** el agente ya navega dentro de la app (clic en menús funciona). Al final
  quedó en la pantalla **"Clientes"** con datos reales (tabla de clientes), no en el home.
- **Sigue fallando E3:** `respuesta: 0` (esperado `45`). Causa: el agente fue a **Clientes** en vez
  de **Facturas** — un problema de **planificación/decisión** (qué submenú elegir), no de grounding.

## 6. Bloqueante restante: planificación (no grounding)

El loop ahora ejecuta los clics que pide; el error es **semántico**: ante "facturas vencidas", el plan
lo lleva a "Clientes". Es el reto central del brief ("aprender a usar la app como empleado nuevo"):
- Mejorar `plan.txt` para que descomponga según el **módulo correcto** (facturas ≠ clientes).
- Que `select`/`check` verifiquen que llegó al módulo esperado (con OCR de contexto) y corrijan.

Próximo paso: afinar `plan`/`select`/`check` con la app real, no más cambios de grounding.

---

# Iteración 3 — Planificación, estado entre pasos, lectura de tablas (E3 ✅)

## 1. Resultado

E3 → `respuesta: 45`, `terminada` (134 s, $0.0055). Los 6 prompts siguen siendo **genéricos** (la app de
evaluación es otra); nada nombra módulos de SIGECOM. Diagnóstico con la nueva traza (`RETO1_TRACE=1`):
el error de "ir a Clientes" venía del plan (hito "seleccionar el cliente en la lista de clientes"), pero
tras corregirlo aparecieron otros 6 bloqueantes que los prompts solos no arreglaban.

## 2. Causas y arreglos

| # | Causa (evidencia) | Arreglo |
|---|---|---|
| 1 | El plan trataba el nombre del cliente como lugar al que navegar | `plan.txt`: entidad objetivo vs filtros; hitos agrupados; `pantalla_esperada` por hito (`Milestone`) |
| 2 | `act()` sin memoria: repetía el mismo clic que cerraba el menú (toggle) | `ActState` + `avoid` (excluye de la lista el elemento recién clicado si aparecieron elementos nuevos); `history` y `feedback` del `check` van al `select` |
| 3 | `check` aprobaba con el menú abierto / sin comparar campos | `check.txt`: pantalla esperada, título, comparación literal de campos, "sin resultados" ⇒ desconfiar, diálogos bloquean |
| 4 | **Cajas de Qwen3-VL en 0–1000** leídas como píxeles → clics intermitentes fuera de sitio | `scale_for()` en `vision/locate.py`; prompt de detección pide 0–1000 y formato compacto |
| 5 | `select_all` roto (`'ctrl'`) y reintentos concatenaban texto | `Control_L`; `type` auto-precedido de Ctrl+A |
| 6 | Lotes truncados a 8 acciones (nunca llegaba a "Buscar") | `max_actions=16`; acción inválida no tumba el lote |
| 7 | `deepseek-v4-flash` agotaba `max_tokens` pensando → HTTP 200 sin JSON → error | `reasoning: {"enabled": false}`; el `else` final del cliente ya no lanza en un 200 reintentable |
| 8 | Modal "Novedades" bloqueaba la app | `select.txt` PRIORIDAD 1: cerrar diálogos informativos |
| 9 | Respuesta falsa `0` (la pantalla era otra) y `respuesta` tomada de hitos fallidos | Solo se lee la respuesta si todos los hitos se verificaron; `null` ⇒ `fallida` sin línea `respuesta:` |
| 10 | El VLM no cuenta/filtra filas fiablemente ni sabe si hay más páginas | `extract_count`: transcribe cada página (235b, en paralelo), el **código** pagina (clic "Siguiente"+diff), un LLM de texto elige ids, el código cuenta; si no se confirma el final ⇒ `None` |
| 11 | Latencia (~35 s/paso) | detección de la pantalla nueva en paralelo con `check` (`prefetched`); `provider.sort=latency`; `check` reutiliza la captura; `MAX_ATTEMPTS` 4→7 para exploración de menús |

## 3. Medido (no supuesto)

| Qué | Resultado |
|---|---|
| Detector 235b vs verdad de terreno (8 elementos) | error máx 8–9 px, 10–19 s |
| Detector 30b | 3 px en una corrida, pero 12–33 s y una corrida con error de 765 px con el prompt compacto ⇒ se queda 235b |
| Transcribir 4 páginas (Σ=45) | 235b: 45 ✔ · 72b: 45 ✔ · 30b: 43 ✘ |
| Lectura directa "cuenta/filtra" con VLM | 37–44 de 45 ✘ (por eso se transcribe y se cuenta en código) |

## 4. Pendiente

E5 (ambigüedad de homónimos ⇒ `fallida` con NITs), y probar E1, E2, E4. Ver `docs/proximo_paso.md`.

---

# Iteración 4 — Ambigüedad, anti-duplicado y robustez (E1–E5 pasan)

| # | Problema (evidencia) | Arreglo |
|---|---|---|
| 1 | E5: ante homónimos el agente intentaba abrir "la ficha" sin reconocer la ambigüedad | `plan.txt` marca el hito de localizar (`localiza_registro`); `agent/disambiguate.py`: transcribe todas las columnas (`table_full`), LLM de texto propone candidatos (`match_rows`), el **código** decide (>1 ⇒ `fallida` nombrando cada fila); falla cerrada si no se puede verificar |
| 2 | Clic en el campo de filtro con el valor escrito en vez de en la fila | `select.txt`: abrir fila = clicar su código/enlace; el hito siguiente recibe la fila identificada como pista |
| 3 | E1: riesgo de doble guardado | `ActState.committed` + `blocked()`: no repetir el mismo botón de confirmación salvo error de validación |
| 4 | E1: guardado correcto reportado como fallo (la app no muestra mensaje; el título pasa a "Cliente CL-xxxx") | `check.txt`/`plan.txt`: varias señales de guardado válidas; un botón de aplicar visible no implica "no guardado" |
| 5 | Excepción `ValueError(3072345193)` de asyncvnc (flujo RFB desincronizado) mató una tarea | `capture.screenshot` reconecta (`client._reconnect`) y reintenta una vez |
| 6 | `Costo:` subestimado | `cost_acc` (contextvar) suma todas las llamadas |
| 7 | `check()` comparaba el frame consigo mismo (diff muerto) | eliminado |
| 8 | Caja pegada al borde (`x1=1` en 0–1000) se leía como fracción | `_to_px` con escala fija |
| 9 | `LLMError` en `act`/`check` tumbaba la tarea | gasta un intento del hito |
| 10 | Prompts/tests con nombres de la app | genéricos (ejemplos "Acme", "Menú A") |

Resultado: E1–E5 pasan `/__check` (una corrida cada una). Pendiente: varianza, deploy, tareas no vistas.
