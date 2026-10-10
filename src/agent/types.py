"""Fase 4: estructuras de datos del agente."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Milestone:
    """Hito del plan: qué hacer y cómo se reconoce la pantalla al cumplirlo."""

    text: str
    expected: str = ""


@dataclass
class TaskResult:
    estado: str  # "terminada" | "fallida"
    resumen: str
    steps: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "estado": self.estado,
            "resumen": self.resumen,
            "steps": self.steps,
            "cost_usd": round(self.cost_usd, 6),
        }
