from .connection import connect, normalize_url
from .capture import screenshot, wait_and_capture
from .input import click, type_text, select_all, press_key, wait_ms

__all__ = [
    "connect",
    "normalize_url",
    "screenshot",
    "wait_and_capture",
    "click",
    "type_text",
    "select_all",
    "press_key",
    "wait_ms",
]