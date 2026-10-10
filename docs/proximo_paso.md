# Próximo paso — E5 (homónimos) y el resto de pruebas oficiales

> Documento de traspaso. Complementa a `AGENTS.md` y `docs/fase_4_hotfix_grounding.md` (Iteración 3).

## Estado

**E3 resuelta** (`¿Cuántas facturas vencidas tiene Ferretería Ruiz?` → `respuesta: 45`, `terminada`,
~134 s, ~$0.006). La causa no era solo de prompts; ver Iteración 3 del hotfix. Tests: 63 en verde
(`PYTHONPATH=src python -m unittest tests.test_model tests.test_agent -v`).

| Prueba | Estado |
|---|---|
| E1 crear cliente | ⬜ no intentada |
| E2 corregir dirección con nota | ⬜ no intentada |
| E3 pregunta → `45` | ✅ (45 / terminada) |
| E4 exportar pedidos entregados sep-2026 | ⬜ no intentada |
| E5 homónimos → `fallida` + NITs | ⚠️ termina `fallida` y NO modifica nada, pero el resumen no nombra los NITs |

## Qué falla ahora

**E5** (`Cambia el teléfono de Ana Torres a 3014445566.`, esperado `fallida` con `52345678` y
`1019876543` en el resumen). El agente llega al listado y ve dos "Ana Torres" (CL-0005, CL-0031),
pero no reconoce la ambigüedad: intenta "abrir la ficha" hasta agotar intentos (`pantalla sin cambios`).
Termina `fallida` por casualidad, sin las claves de razón. Falta una **detección explícita de
ambigüedad**: cuando una búsqueda devuelve >1 registro que coincide con el nombre de la tarea y nada
en la tarea los distingue, abortar con `fallida` y nombrar los identificadores (NIT/código) de cada uno.
Sitio natural: un paso de "desambiguación" tras filtrar (leer la tabla con `_ask_table`, ya existe) en
vez de seguir con acciones de escritura.

Luego intentar E1, E2 y E4 (E4 requiere filtros de fecha + estado + botón Exportar; el conteo/tabla ya
está cubierto, la exportación no).

## Cosas que aprendimos (no redescubrir)

- **Qwen3-VL devuelve cajas en escala 0–1000**, no 0–1 ni píxeles. Antes se interpretaba mal y daba
  clics fuera de lugar de forma intermitente. Ahora `vision/locate.py` divide entre 1000 (error ≤9 px).
- **El escritorio ignora input unos segundos tras conectar** (4 s no basta, 15 s sí). El plan (~20 s)
  lo cubre; si algún día la primera acción se adelanta, perderá el primer clic.
- **`select_all` estaba roto** (`'ctrl'` no es un keysym de asyncvnc → `Control_L`). `type` ahora hace
  Ctrl+A antes (idempotente ante reintentos).
- **`deepseek-v4-flash` es de razonamiento**: sus tokens de pensamiento truncaban el JSON. Se desactiva
  con `reasoning: {"enabled": false}` (en `model/client.py`).
- **Leer tablas**: 30b omite filas; 235b y 72b dan 45 exacto (`spikes/table_bench.py`). Se transcribe y
  el filtrado/conteo se hace en código (+ LLM de texto para el predicado), nunca "contando" con el VLM.
- **Paginación la decide el código** (clic en "Siguiente" + diff), no el VLM (que alucinaba
  `hay_mas_paginas`/`total_visible`).
- **La app cambia entre corridas**: aparece un modal "Novedades v4.2" a veces, y el botón "Buscar" a veces
  se llama "Filtrar". Los prompts son genéricos por eso.
- **Definición de "vencida"**: `Estado == "Vencida"` con nombre EXACTO. "Pendiente" con fecha pasada no
  cuenta y "Ferretería Ruiz e Hijos" es otro cliente (la búsqueda es "contiene").
- **Latencia**: el detector (235b) tarda 4–45 s según el proveedor. Se mitiga lanzando la detección de la
  pantalla nueva en paralelo con el `check` (`prefetched` en `act()`), y `provider.sort=latency`.

## Cómo verificar

```bash
cd /home/kevin/RETO1FRONTIER && source .venv/bin/activate && set -a && source .env && set +a
RETO1_TRACE=1 PYTHONPATH=src python spikes/live_agent_test.py "<tarea>" --reset   # traza por paso a stderr
PYTHONPATH=src python -m unittest tests.test_model tests.test_agent -v
```

Spikes útiles (usan `spikes/captures/`, gitignored, local): `detector_bench.py` (precisión/latencia del
detector vs verdad de terreno), `table_bench.py` (transcripción de tablas), `dump_client_pages.py`
(captura todas las páginas de facturas de un cliente para leerlas a mano).

## Referencias

1. `AGENTS.md` · 2. `docs/fase_4_hotfix_grounding.md` · 3. `docs/plan_implementacion.md` *(gitignored)* ·
4. `RETO1_CONTEXTO.md`, `frontier-reto-1/` *(gitignored)*.
