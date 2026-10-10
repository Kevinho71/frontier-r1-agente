"""Fase 4: loop del agente plan→act→check sobre píxeles."""

from .loop import run_task
from .redact import env_secrets, redact_text
from .summarize import extract_answer, format_summary, is_question
from .types import TaskResult

__all__ = [
    "run_task",
    "TaskResult",
    "is_question",
    "extract_answer",
    "format_summary",
    "redact_text",
    "env_secrets",
]
