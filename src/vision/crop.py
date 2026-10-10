"""Vision: recorte y re-encuadre del framebuffer para ahorrar tokens."""

import base64
import io

import numpy as np
from PIL import Image


def crop_region(
    frame: np.ndarray,
    x: int = 0,
    y: int = 0,
    width: int | None = None,
    height: int | None = None,
    margin: int = 0,
) -> np.ndarray:
    """
    Recorta una region del framebuffer, acotada a sus dimensiones.

    Si se pasa margin>0, expande un cuadrado de lado 2*margin alrededor de
    (x,y) (ignora width/height). Util para ventana de atencion.
    """
    h, w = frame.shape[:2]
    if margin > 0:
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(w, x + margin)
        y2 = min(h, y + margin)
        return frame[y1:y2, x1:x2]
    x2 = min(w, x + width) if width is not None else w
    y2 = min(h, y + height) if height is not None else h
    return frame[y:y2, x:x2]


def downscale(frame: np.ndarray, max_width: int = 800) -> np.ndarray:
    """Reduce la imagen para orientacion, manteniendo proporcion."""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    new_w = int(w * scale)
    new_h = int(h * scale)
    return np.asarray(Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS))


def to_data_url(frame: np.ndarray, format: str = "jpeg", quality: int = 85) -> str:
    """Convierte un framebuffer RGBA a data URL para enviar al modelo."""
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    if format == "png":
        img.save(buf, format="PNG")
        mime = "image/png"
    else:
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality)
        mime = "image/jpeg"
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:{mime};base64,{b64}"