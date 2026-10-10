"""Vision: OCR barato vía modelo de visión (OpenRouter)."""

import os

import httpx

from .crop import to_data_url

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OCR_MODEL = "inclusionai/ling-3.0-flash-vl"


async def extract_text(
    frame,
    model: str = DEFAULT_OCR_MODEL,
    prompt: str = "Transcribe únicamente el texto visible de la pantalla, tal cual.",
) -> str:
    """Lee el texto visible de un framebuffer usando un modelo barato de visión."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY no está definida")

    data_url = to_data_url(frame)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()