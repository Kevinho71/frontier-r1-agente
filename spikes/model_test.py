"""Smoke test de Fase 3: verifica contra OpenRouter que los IDs del catálogo existen.

Requiere OPENROUTER_API_KEY en el entorno. No opera el escritorio; solo valida
que el cliente devuelva JSON bien formado y usage/cost poblados.

Uso:
    PYTHONPATH=src OPENROUTER_API_KEY=... python spikes/model_test.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model import Capability, chat, chat_vision, load_prompt, select  # noqa: E402
from model.registry import CANDIDATES  # noqa: E402


async def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Falta OPENROUTER_API_KEY. Seteá la variable y reintentá.")
        return 2

    print("Catálogo:", {c.value: v for c, v in CANDIDATES.items()})

    plan_model = select(Capability.PLAN)
    print(f"\n[PLAN] {plan_model}")
    prompt = load_prompt("plan", task="Mostrar el listado de clientes")
    res = await chat(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        plan_model,
        max_tokens=256,
        json_mode=True,
    )
    print(f"  parsed={res.parsed!r}")
    print(f"  tokens in/out={res.prompt_tokens}/{res.completion_tokens} cost=${res.cost_usd:.6f}")

    check_model = select(Capability.CHECK)
    print(f"\n[CHECK] {check_model} (solo verifica que el ID responde)")

    return 0 if res.parsed is not None else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
