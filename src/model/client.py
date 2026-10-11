"""Cliente OpenRouter con retry/backoff, JSON defensivo y cost tracking."""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import random
from dataclasses import dataclass

import httpx

from .registry import price_for
from .router import mark_exhausted

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 3

# Modelos "thinking" cuyos tokens de razonamiento consumen max_tokens (y truncan el JSON).
# Para planificar/decidir no hace falta razonar: se desactiva (más rápido y barato).
_NO_REASONING_PREFIXES = ("deepseek/",)


# Acumulador de costo por tarea: cada llamada exitosa suma su costo estimado a la lista del
# contexto actual (las sub-tareas asyncio comparten la misma lista), así el total es completo.
cost_acc: contextvars.ContextVar = contextvars.ContextVar("cost_acc", default=None)


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        exhausted: bool = False,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.exhausted = exhausted


@dataclass
class LLMResult:
    content: str
    parsed: dict | None
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY no está definida")
    return key


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _backoff(attempt: int) -> float:
    """Backoff exponencial (2^n s) + jitter 0..0.5s."""
    return (2 ** attempt) + random.uniform(0, 0.5)


def _retryable(body) -> bool:
    """Lee `error.metadata.retryable` (o `error.retryable`) de una respuesta 429."""
    err = body.get("error") or {}
    if isinstance(err, dict):
        if "retryable" in err:
            return bool(err["retryable"])
        meta = err.get("metadata") or {}
        if isinstance(meta, dict) and "retryable" in meta:
            return bool(meta["retryable"])
    return True


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {}


def _extract_json(text: str) -> dict | None:
    """Extrae el primer objeto JSON de una respuesta (respaldo ante texto con relleno)."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = price_for(model)
    return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout


def _parse(data: dict, model: str) -> LLMResult:
    choice = data["choices"][0]
    message = choice["message"]
    content = (message.get("content") or "").strip()
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return LLMResult(
        content=content,
        parsed=_extract_json(content),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=_estimate_cost(model, prompt_tokens, completion_tokens),
    )


async def chat(
    messages,
    model: str,
    *,
    max_tokens: int = 1024,
    json_mode: bool = True,
    temperature: float = 0.0,
    timeout: float = 60.0,
    retries: int = MAX_RETRIES,
    provider: dict | None = None,
) -> LLMResult:
    """Llamada a chat completions con retry/backoff y agotamiento en 429 no retryable.

    `messages` sigue el formato OpenRouter (admite contenido multimodal con
    `image_url` data-URL). Si `json_mode`, envía `response_format` json_object;
    el parseo es defensivo de todos modos.
    """
    if not model:
        raise LLMError("sin modelo disponible (todos los candidatos están agotados)")
    api_key = _api_key()
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if provider:
        payload["provider"] = provider  # p. ej. {"sort": "latency"}
    if model.startswith(_NO_REASONING_PREFIXES):
        payload["reasoning"] = {"enabled": False}

    last_err: LLMError | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(OPENROUTER_URL, json=payload, headers=_headers(api_key))
            if resp.status_code == 200:
                result = _parse(resp.json(), model)
                if json_mode and result.parsed is None:
                    last_err = LLMError(f"{model}: respuesta sin JSON válido", retryable=True)
                else:
                    acc = cost_acc.get()
                    if acc is not None:
                        acc.append(result.cost_usd)
                    return result
            elif resp.status_code == 429:
                if not _retryable(_safe_json(resp)):
                    mark_exhausted(model)
                    raise LLMError(f"{model}: cuota agotada (429)", exhausted=True)
                last_err = LLMError(f"{model}: 429 rate-limit", retryable=True)
            elif resp.status_code == 404:
                mark_exhausted(model)
                raise LLMError(f"{model}: modelo no encontrado (404)", exhausted=True)
            elif 500 <= resp.status_code < 600:
                last_err = LLMError(f"{model}: HTTP {resp.status_code}", retryable=True)
            else:
                raise LLMError(f"{model}: HTTP {resp.status_code} {resp.text[:200]}")
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_err = LLMError(f"{model}: {exc!r}", retryable=True)

        if attempt < retries:
            await asyncio.sleep(_backoff(attempt))

    raise last_err or LLMError(f"{model}: fallo desconocido")


TEXT_FALLBACK = "qwen/qwen3-vl-235b-a22b-instruct"


async def chat_text(messages, model: str, **kw) -> LLMResult:
    """Llamada de solo texto con respaldo: si el modelo primario falla (JSON inválido, 5xx,
    agotado), reintenta una vez con un modelo distinto en vez de perder el paso."""
    models = [m for m in (model, TEXT_FALLBACK) if m]
    last: LLMError | None = None
    for i, m in enumerate(dict.fromkeys(models)):
        try:
            return await chat(messages, m, **{**kw, "retries": 1 if i == 0 and len(models) > 1 else kw.get("retries", MAX_RETRIES)})
        except LLMError as exc:
            last = exc
    raise last or LLMError("sin modelo disponible")


async def chat_vision(
    text: str,
    frame,
    model: str,
    *,
    max_tokens: int = 512,
    json_mode: bool = False,
    downscale_to: int | None = None,
    temperature: float = 0.0,
    timeout: float = 60.0,
    retries: int = MAX_RETRIES,
    provider: dict | None = None,
) -> LLMResult:
    """Envía texto + captura (framebuffer RGBA) a un modelo de visión."""
    from vision.crop import downscale, to_data_url

    img = frame
    if downscale_to is not None:
        img = downscale(frame, max_width=downscale_to)
    data_url = to_data_url(img)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    return await chat(
        messages,
        model,
        max_tokens=max_tokens,
        json_mode=json_mode,
        temperature=temperature,
        timeout=timeout,
        retries=retries,
        provider=provider,
    )
