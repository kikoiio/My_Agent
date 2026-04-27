#!/usr/bin/env python3
"""Multi-Persona Voice Agent — CLI entry point.

Usage:
    python main.py [--persona assistant]

Type messages to chat with the agent. /quit to exit.
"""

from __future__ import annotations

import asyncio
import argparse
from pathlib import Path

from core.breaker import CircuitBreaker
from core.loop import AgentLoopContext, agent_loop
from core.persona import load as load_persona
from core.types import AgentState
from backend.litellm.client import create_llm_callable
from backend.memory.store import MemoryStore
from backend.observe.tracer import Tracer


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Persona Voice Agent CLI")
    parser.add_argument(
        "--persona", default="assistant", help="Persona name (default: assistant)"
    )
    parser.add_argument(
        "--personas-dir",
        default="personas",
        help="Personas root directory (default: personas)",
    )
    args = parser.parse_args()

    persona_dir = Path(args.personas_dir) / args.persona
    if not persona_dir.is_dir():
        print(f"Persona not found: {persona_dir}")
        print("Available personas:")
        from core.persona import list_personas
        for name in list_personas(Path(args.personas_dir)):
            print(f"  - {name}")
        return

    # Load persona
    persona = load_persona(persona_dir)
    print(f"Loaded persona: {persona.name}")
    print(f"  system_prompt: {persona.system_prompt[:80]}...")

    # Initialize components
    memory_store = MemoryStore("data/memory.db")
    tracer = Tracer("data/traces.db")
    circuit_breaker = CircuitBreaker()

    # Create LLM callable (default_fast model)
    llm_call = create_llm_callable(role="default_fast")

    # Build agent loop context
    state = AgentState(persona=persona.name, user_id="owner")
    ctx = AgentLoopContext(
        state=state,
        persona=persona,
        circuit_breaker=circuit_breaker,
        memory_store=memory_store,
        tracer=tracer,
        llm_call=llm_call,
    )

    print(f"\n{'='*50}")
    print(f"  小安 (Xiao An) — 你的私人助理")
    print(f"  输入消息开始对话，/quit 退出")
    print(f"{'='*50}\n")

    asyncio.run(_chat_loop(ctx))


async def _chat_loop(ctx: AgentLoopContext) -> None:
    """Interactive chat loop."""
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        response, new_state, trace_id = await agent_loop(ctx, user_input)

        # Update context state for next turn
        ctx.state = new_state

        print(f"\n小安: {response}")
        print(f"  [{trace_id}]\n")


if __name__ == "__main__":
    main()
