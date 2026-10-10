"""Vision: OCR barato vía modelo de visión (OpenRouter)."""

from model.client import chat_vision

DEFAULT_OCR_MODEL = "inclusionai/ling-3.0-flash-vl"


async def extract_text(
    frame,
    model: str = DEFAULT_OCR_MODEL,
    prompt: str = "Transcribe únicamente el texto visible de la pantalla, tal cual.",
) -> str:
    """Lee el texto visible de un framebuffer usando un modelo barato de visión."""
    result = await chat_vision(
        prompt,
        frame,
        model,
        max_tokens=512,
        json_mode=False,
    )
    return result.content
