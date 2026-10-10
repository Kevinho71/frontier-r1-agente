"""Fase 3: routing de modelos + cliente OpenRouter + prompts."""

from .client import LLMError, LLMResult, chat, chat_vision, cost_acc
from .prompts import load_prompt
from .registry import CANDIDATES, PRICES, Capability, price_for
from .router import is_exhausted, mark_exhausted, reset, select

__all__ = [
    "Capability",
    "select",
    "mark_exhausted",
    "is_exhausted",
    "reset",
    "chat",
    "chat_vision",
    "cost_acc",
    "LLMResult",
    "LLMError",
    "load_prompt",
    "CANDIDATES",
    "PRICES",
    "price_for",
]
