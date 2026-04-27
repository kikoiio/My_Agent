"""LangGraph main graph: draft → critic → respond.

Per plan.md §10.2:
- Draft node: Generate initial response
- Critic node: Check persona consistency + safety
- Respond node: Finalize and prepare output

Uses langgraph if installed; falls back to sequential execution otherwise.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["build_main_graph", "run_graph", "MainGraphState"]

logger = logging.getLogger(__name__)

# Try importing langgraph; fall back gracefully
try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    logger.debug("langgraph not installed, using sequential fallback")


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
    """Generate initial draft response."""
    system_msg = "You are a helpful assistant."

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
    """Critique draft for persona consistency and safety."""
    criticism = []

    if security_guard:
        wrapped = security_guard.wrap_external(
            state.draft_response,
            source="agent_response",
        )
        if not security_guard.is_safe(wrapped):
            criticism.append("Response contains potential injection patterns")
            state.is_safe = False

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
    """Finalize response preparation."""
    if not state.is_safe or state.criticism:
        state.final_response = (
            f"[Critique detected: {'; '.join(state.criticism)}] "
            f"Original response suppressed for safety."
        )
    else:
        state.final_response = state.draft_response

    return state


def build_main_graph(llm_call: Any, security_guard: Any = None) -> Any:
    """Build LangGraph main graph (draft → critic → respond).

    Uses langgraph StateGraph if available, falls back to dict-based
    sequential execution.

    Args:
        llm_call: LLM callable (system_msg, user_msg, persona) -> str
        security_guard: Optional security Guard instance

    Returns:
        Compiled langgraph graph or dict-based fallback
    """
    if HAS_LANGGRAPH:
        return _build_langgraph(llm_call, security_guard)
    return _build_fallback(llm_call, security_guard)


def _build_langgraph(llm_call: Any, security_guard: Any = None) -> Any:
    """Build real langgraph StateGraph."""
    builder = StateGraph(MainGraphState)

    async def draft_wrapper(state: MainGraphState) -> MainGraphState:
        return await draft_node(state, llm_call)

    async def critic_wrapper(state: MainGraphState) -> MainGraphState:
        return await critic_node(state, llm_call, security_guard)

    async def respond_wrapper(state: MainGraphState) -> MainGraphState:
        return await respond_node(state)

    builder.add_node("draft", draft_wrapper)
    builder.add_node("critic", critic_wrapper)
    builder.add_node("respond", respond_wrapper)

    builder.set_entry_point("draft")
    builder.add_edge("draft", "critic")
    builder.add_edge("critic", "respond")
    builder.add_edge("respond", END)

    return builder.compile()


def _build_fallback(llm_call: Any, security_guard: Any = None) -> dict:
    """Build dict-based fallback graph (sequential execution)."""
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
        "_langgraph_fallback": True,
    }


async def run_graph(
    graph: Any,
    input_text: str,
    persona: str,
    user_id: str = "owner",
    trace_id: str = "",
) -> MainGraphState:
    """Execute graph on input.

    Works with both langgraph compiled graphs and dict-based fallback.

    Args:
        graph: Compiled graph (from build_main_graph) or dict fallback
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

    # langgraph compiled graph
    if HAS_LANGGRAPH and not isinstance(graph, dict):
        return await graph.ainvoke(state)

    # Dict-based fallback: run nodes sequentially
    nodes = graph.get("nodes", {})
    if "draft" in nodes:
        state = await nodes["draft"](state)
    if "critic" in nodes:
        state = await nodes["critic"](state)
    if "respond" in nodes:
        state = await nodes["respond"](state)

    return state


async def _call_llm_async(llm_call: Any, system: str, user_msg: str, persona: str) -> str:
    """Async wrapper for LLM calls."""
    import asyncio

    return await asyncio.to_thread(llm_call, system, user_msg, persona)
