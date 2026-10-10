# Próximo paso — deploy y robustez

> Documento de traspaso. Complementa a `AGENTS.md` y `docs/fase_4_hotfix_grounding.md`.

## Estado

Las 5 pruebas oficiales pasan `/__check` contra el escritorio de pruebas (1 corrida cada una, ~$0.01–0.02
por tarea, 12–18 pasos). Tests sin red: 83 en verde.

| Prueba | Resultado |
|---|---|
| E1 crear cliente | ✅ terminada, sin duplicados |
| E2 corregir dirección | ✅ terminada |
| E3 pregunta | ✅ `respuesta: 45` |
| E4 exportar septiembre | ✅ terminada (filtros + Exportar) |
| E5 homónimos | ✅ fallida, resumen nombra CL-0005/CL-0031 con sus NIT |

API (`src/api`) y logs (`src/logs`) hechos; E3 verificado a través del servicio local. Imagen Docker
construida y probada (`/health`, 401 sin token).

## Pendiente (en orden)

1. **Deploy (Fase 7):** subir la imagen a Railway/Fly (contenedor persistente). Variables: `TEAM_TOKEN`,
   `OPENROUTER_API_KEY`, opcional `DATA_DIR` (volumen), `MAX_CONCURRENT`. Luego `GET /health` y un POST real.
2. **Medir varianza:** repetir cada prueba 3–5 veces (con `--reset`) y registrar tasa de éxito. Una
   corrida por prueba no es evidencia de fiabilidad.
3. **Falsos éxitos:** `terminada` = "el verificador visual (VLM) lo aprobó". Idea pendiente: tras guardar,
   releer el registro desde el listado y comparar.
4. **Generalización:** probar con tareas no vistas (otras entidades, borrar, fechas relativas, dos datos en
   `respuesta:`). Los prompts son genéricos, pero solo se han ejercitado con esta app.
5. **Costo/latencia:** ~20 s de plan + ~12 s por paso; las tareas largas se acercan a los 250 s útiles.

## Cosas que aprendimos (no redescubrir)

- **Qwen3-VL devuelve cajas en escala 0–1000**; el código convierte y clica el centro de la caja.
- **El escritorio ignora input unos segundos tras conectar**; el plan (~20 s) lo cubre.
- **`deepseek-v4-flash` es de razonamiento**: se desactiva con `reasoning: {"enabled": false}`.
- **Leer tablas**: 235b/72b transcriben bien, 30b omite filas. El conteo lo hace el código.
- **La app cambia entre corridas** (modal de novedades, "Buscar"/"Filtrar"): prompts genéricos.
- **Tras guardar, la app puede no mostrar mensaje**: el formulario pasa a "Cliente CL-xxxx" y el botón
  sigue visible. `check.txt` acepta varias señales de guardado.
- **Desincronización RFB** (visto una vez: `ValueError` con codificación basura): `desktop.capture.screenshot`
  reconecta y reintenta una vez.
- **Un fallo de LLM en `act`/`check`** gasta un intento del hito, no la tarea.

## Cómo verificar

```bash
cd /home/kevin/RETO1FRONTIER && source .venv/bin/activate && set -a && source .env && set +a
RETO1_DUMP=/tmp/x RETO1_TRACE=1 PYTHONPATH=src python spikes/live_agent_test.py "<tarea>" --reset
curl -s -X POST -H "Authorization: Bearer $TOKEN_ESCRITORIO" -H "Content-Type: application/json" \
  -d @frontier-reto-1/pruebas/E1-crear-cliente.json <URL_ESCRITORIO>/__check
PYTHONPATH=src python -m unittest tests.test_model tests.test_agent tests.test_api -v
```

Ojo: `/__check` justo después de `--reset` da `pass:false` en tareas con cambios (es el estado base).
