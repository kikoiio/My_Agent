"""Agent main loop: pure function integrating router, breaker, persona, memory.

Per plan.md §6: Single-turn agent loop that:
1. Accepts (persona, messages, state) → routes to chat/dream/memory_writer
2. Applies circuit breaker for safety
3. Calls LLM brain (via LangGraph or direct)
4. Stores result in memory
5. Returns (response, new_state, trace_id)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from core.breaker import CircuitBreaker
from core.persona import Persona
from core.router import route
from core.types import AgentState, Message

__all__ = ["AgentLoopContext", "agent_loop"]


@dataclass
class AgentLoopContext:
    """Context passed through agent loop."""

    state: AgentState
    persona: Persona
    circuit_breaker: CircuitBreaker
    memory_store: Any  # MemoryStore
    tracer: Any  # Tracer
    llm_call: Callable[[str, str, Persona], str]  # (system, user_msg, persona) -> response


async def agent_loop(
    ctx: AgentLoopContext,
    user_message: str,
    image_bytes: bytes | None = None,
) -> tuple[str, AgentState, str]:
    """Execute single agent turn.

    Args:
        ctx: Agent loop context with all dependencies
        user_message: User input text
        image_bytes: Optional image for multimodal input

    Returns:
        (response_text, updated_state, trace_id)
    """
    trace_id = str(uuid.uuid4())[:12]

    # Initialize session and trace
    ctx.memory_store.session_init(ctx.state.user_id, ctx.state.persona)
    ctx.tracer.trace_add(
        trace_id=trace_id,
        persona=ctx.state.persona,
        user_id=ctx.state.user_id,
        session_id=ctx.state.user_id,
        role=ctx.state.role,
        input_messages_count=len(ctx.state.messages),
    )

    # Check circuit breaker
    if not ctx.circuit_breaker.is_healthy():
        error_msg = f"Circuit breaker open: {ctx.circuit_breaker.trip_reason}"
        ctx.tracer.trace_set_error(trace_id, error_msg)
        return error_msg, ctx.state, trace_id

    # Add user message to state
    new_messages = ctx.state.messages.copy()
    new_messages.append(
        Message(
            role="user",
            content=user_message,
            name=ctx.state.user_id,
        )
    )

    # Determine routing
    routed_role = route(ctx.state.role, user_message, image_bytes is not None)
    updated_state = ctx.state
    updated_state.role = routed_role
    updated_state.messages = new_messages
    updated_state.has_image = image_bytes is not None
    updated_state.trace_id = trace_id

    # Get system prompt from persona
    system_prompt = ctx.persona.system_prompt

    # Build conversation context from recent messages
    message_context = "\n".join(
        f"{m.role}: {m.content}" for m in new_messages[-5:]  # Last 5 messages
    )

    try:
        # Call LLM via chosen route
        response = await asyncio.to_thread(
            ctx.llm_call,
            system_prompt,
            message_context,
            ctx.persona,
        )

        # Add assistant response to messages
        updated_state.messages.append(
            Message(
                role="assistant",
                content=response,
            )
        )

        # Store in episodic memory
        ctx.memory_store.episode_add(
            user_id=ctx.state.user_id,
            persona=ctx.state.persona,
            event_type="conversation",
            content=f"User: {user_message}\nAgent: {response}",
            metadata={
                "trace_id": trace_id,
                "role": routed_role,
                "input_tokens": _estimate_tokens(message_context),
                "output_tokens": _estimate_tokens(response),
            },
        )

        # Update tracer with success
        ctx.tracer.trace_update_tokens(trace_id, len(response.split()))

        # Record event
        ctx.tracer.event_add(
            event_id=f"{trace_id}_llm_call",
            span_id=f"{trace_id}_span_main",
            trace_id=trace_id,
            event_type="llm_call_complete",
            metadata={
                "model": ctx.persona.name,
                "response_length": len(response),
            },
        )

        return response, updated_state, trace_id

    except Exception as e:
        error_msg = f"Agent loop error: {str(e)}"
        ctx.tracer.trace_set_error(trace_id, error_msg)
        ctx.circuit_breaker.trip(reason=str(e))
        return error_msg, updated_state, trace_id


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ≈ 4 chars)."""
    return max(1, len(text) // 4)
