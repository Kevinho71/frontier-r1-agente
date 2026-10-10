# Fase 2 — Síntesis: `src/vision/` (percepción barata)

## Qué se realizó

Percepción sobre el framebuffer, previa al modelo de visión, para ahorrar tokens y verificar barato:

| Archivo | Qué expone |
|---|---|
| `crop.py` | `crop_region()`, `downscale()`, `to_data_url()` |
| `diff.py` | `frame_signature()`, `diff_fraction()`, `changed()` |
| `ocr.py` | `extract_text()` (modelo barato `ling-3.0-flash-vl`) |

## Qué cambió respecto a antes

- **Antes:** `crop_region()` vivía en `src/desktop/capture.py` (mezclado con I/O); no había diff
  ni OCR.
- **Ahora:** `crop` se movió a `vision/` (es procesamiento de imagen, no I/O de escritorio), y se
  añadieron `diff` y `ocr`.
- **Cambio de decisión:** el umbral de `changed()` bajó de **1% a 0.1%**.

## Decisiones de diseño (y por qué)

1. **`crop` en `visión`, no en `desktop`.**
   `desktop/` = primitivas de I/O (capturar, clicar). `vision/` = transformación de la imagen
   (recortar, re-encuadrar, comparar). Separar por responsabilidad evita acoplar el framebuffer
   crudo con la lógica del agente.

2. **Umbral de `changed()` en 0.1% (no 1%).**
   Medimos que abrir un menú desplegable cambia solo **~0.25%** de los píxeles de la pantalla;
   con 1% ese cambio se perdía. Como el "sin cambio" real da **0.0** exacto (no hay ruido de
   compresión), 0.1% es sensible sin falsos positivos.

3. **Verificación por región `box`, no por frame entero.**
   Cambios chicos (un dropdown, un campo que se llena) son casi invisibles en el diff global.
   Comparar solo la región de interés (ej. el área bajo el menú clickeado) da una señal fuerte.

4. **OCR con un modelo $0.021/M.**
   Leer texto directamente es la verificación más barata que existe (confirmar "¿aparece
   'Exportar'?" sin un LLM caro). Además da contexto de orientación (qué menús hay) para el
   grounding. Es la base del `CHECK` en cascada.

5. **`to_data_url` JPEG por defecto (no PNG).**
   JPEG es 3–5× más liviano en tokens de imagen y suficiente para el modelo; PNG solo si se
   necesita nitidez de texto pequeño.

## Validación (contra el escritorio real)

- `changed()` sin acción → `False`, fracción `0.0`.
- `changed()` tras clic en "Comercial" → `True`, fracción `0.00248`.
- OCR del home leyó exacto: `SIGECOM · Distribuidora Andina v3.9 / Hoy: 14/10/2026 · Usuario:
  operador2 / Archivo Comercial Cartera Herramientas Ayuda`.
- `downscale(800)` y `crop_region` con shapes correctos.