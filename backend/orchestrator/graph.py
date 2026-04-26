"""LangGraph main graph: draft → critic → respond.

Per plan.md §10.2:
- Draft node: Generate initial response
- Critic node: Check persona consistency + safety
- Respond node: Finalize and prepare output
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_main_graph", "run_graph"]


class MainGraphState:
    """State passed through graph nodes."""

    def __init__(self):
        self.input_text: str = ""
        self.persona: str = ""
        self.user_id: str = ""
        self.draft_response: str = ""
        self.criticism: list[str] = []
        self.is_safe: bool = True
        self.final_response: str = ""
        self.tools_called: list[str] = []
        self.trace_id: str = ""


async def draft_node(state: MainGraphState, llm_call: Any) -> MainGraphState:
    """Generate initial draft response.

    Args:
        state: Graph state
        llm_call: LLM callable

    Returns:
        Updated state with draft_response
    """
    # Get system prompt (would come from persona)
    system_msg = "You are a helpful assistant."

    # Generate draft
    draft = await _call_llm_async(
        llm_call,
        system_msg,
        state.input_text,
        state.persona,
    )

    state.draft_response = draft
    return state


async def critic_node(
    state: MainGraphState,
    llm_call: Any,
    security_guard: Any = None,
) -> MainGraphState:
    """Critique draft for persona consistency and safety.

    Args:
        state: Graph state
        llm_call: LLM callable
        security_guard: Optional security guard for injection detection

    Returns:
        Updated state with criticism and is_safe flag
    """
    criticism = []

    # Check safety if guard provided
    if security_guard:
        wrapped = security_guard.wrap_external(
            state.draft_response,
            source="agent_response",
        )
        if not security_guard.is_safe(wrapped):
            criticism.append("Response contains potential injection patterns")
            state.is_safe = False

    # Check persona consistency
    # Placeholder: would call LLM to evaluate
    consistency_prompt = f"""Evaluate if this response maintains the persona:
PERSONA: {state.persona}
RESPONSE: {state.draft_response}

Is the response consistent with the persona? (yes/no)"""

    consistency_check = await _call_llm_async(
        llm_call,
        "You are evaluating response consistency.",
        consistency_prompt,
        state.persona,
    )

    if "no" in consistency_check.lower():
        criticism.append("Response breaks persona")

    state.criticism = criticism
    return state


async def respond_node(state: MainGraphState) -> MainGraphState:
    """Finalize response preparation.

    Args:
        state: Graph state

    Returns:
        Updated state with final_response
    """
    # If criticisms exist and safety is at risk, use safer version
    if not state.is_safe or state.criticism:
        state.final_response = (
            f"[Critique detected: {'; '.join(state.criticism)}] "
            f"Original response suppressed for safety."
        )
    else:
        state.final_response = state.draft_response

    return state


def build_main_graph(llm_call: Any, security_guard: Any = None) -> Any:
    """Build LangGraph main graph.

    Note: This is a placeholder. Real implementation would use langgraph library.

    Args:
        llm_call: LLM callable
        security_guard: Optional security guard

    Returns:
        Graph object (placeholder dict)
    """
    return {
        "nodes": {
            "draft": lambda state: draft_node(state, llm_call),
            "critic": lambda state: critic_node(state, llm_call, security_guard),
            "respond": lambda state: respond_node(state),
        },
        "edges": [
            ("draft", "critic"),
            ("critic", "respond"),
        ],
    }


async def run_graph(
    graph: Any,
    input_text: str,
    persona: str,
    user_id: str = "owner",
    trace_id: str = "",
) -> MainGraphState:
    """Execute graph on input.

    Args:
        graph: Graph object
        input_text: User input
        persona: Persona name
        user_id: User ID
        trace_id: Trace ID for observability

    Returns:
        Final graph state
    """
    state = MainGraphState()
    state.input_text = input_text
    state.persona = persona
    state.user_id = user_id
    state.trace_id = trace_id

    # Placeholder: would use actual langgraph execution
    # For now, run nodes sequentially
    if "draft" in graph["nodes"]:
        state = await graph["nodes"]["draft"](state)
    if "critic" in graph["nodes"]:
        state = await graph["nodes"]["critic"](state)
    if "respond" in graph["nodes"]:
        state = await graph["nodes"]["respond"](state)

    return state


async def _call_llm_async(llm_call: Any, system: str, user_msg: str, persona: str) -> str:
    """Async wrapper for LLM calls."""
    import asyncio

    return await asyncio.to_thread(llm_call, system, user_msg, persona)
