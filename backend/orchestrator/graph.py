"""LangGraph main graph: draft → (tool_decide ⇄ tool_execute)* → critic → respond.

Per plan.md §10.2 + 2026-04-27 tool-calling extension:
- draft_node: legacy single-turn draft (used when no ToolRegistry is wired)
- tool_decide_node: ask LLM (with tool schemas) what to do next
- tool_execute_node: dispatch tool calls; loop back to tool_decide
- critic_node: persona consistency + safety check
- respond_node: finalize output

Uses langgraph if installed; falls back to dict-based sequential execution.
`MainGraphState` is a TypedDict (LangGraph's preferred state type) so node
returns are partial dicts and the framework merges them.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

__all__ = [
    "build_main_graph",
    "run_graph",
    "MainGraphState",
    "draft_node",
    "tool_decide_node",
    "tool_execute_node",
    "critic_node",
    "respond_node",
    "make_initial_state",
    "MAX_TOOL_ITERS",
]

logger = logging.getLogger(__name__)

MAX_TOOL_ITERS = 3  # safety cap on tool-calling rounds per turn

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    HAS_LANGGRAPH = False
    logger.debug("langgraph not installed, using sequential fallback")


class MainGraphState(TypedDict, total=False):
    """State passed through graph nodes.

    `total=False` so node returns can be partial-state dicts that LangGraph
    merges into the running state. Test helpers and `make_initial_state()`
    populate the full set of fields up front.
    """

    input_text: str
    persona: str
    active_persona_id: str  # persona 目录名，用于 L2 记忆路由（如 "xiaolin", "assistant"）
    user_id: str
    draft_response: str
    criticism: list[str]
    is_safe: bool
    final_response: str
    tools_called: list[str]
    tool_results: list[dict]
    tool_iter: int
    messages: list[dict]
    pending_tool_calls: list[dict]
    trace_id: str


def make_initial_state(
    *,
    input_text: str = "",
    persona: str = "",
    active_persona_id: str = "",
    user_id: str = "",
    trace_id: str = "",
) -> MainGraphState:
    """Build a fully-populated MainGraphState for a new turn.

    `active_persona_id` is the persona directory key (e.g. "xiaolin") used to
    route L2 episodic memory reads/writes.  Defaults to `persona` when omitted.
    """
    return {
        "input_text": input_text,
        "persona": persona,
        "active_persona_id": active_persona_id or persona,
        "user_id": user_id,
        "draft_response": "",
        "criticism": [],
        "is_safe": True,
        "final_response": "",
        "tools_called": [],
        "tool_results": [],
        "tool_iter": 0,
        "messages": [],
        "pending_tool_calls": [],
        "trace_id": trace_id,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _call_llm_async(
    llm_call: Any,
    system: str,
    user_msg: str,
    persona: str,
) -> str:
    """Run a sync (system, user_msg, persona) -> str callable in a thread."""
    import asyncio

    return await asyncio.to_thread(llm_call, system, user_msg, persona)


async def _call_llm_with_tools_async(
    llm_call_with_tools: Any,
    messages: list[dict],
    tools: list[dict] | None,
    persona: str,
) -> dict:
    """Run the tool-aware LLM callable.

    The callable may be sync or async; both shapes are tolerated.
    """
    import asyncio
    import inspect as _inspect

    if _inspect.iscoroutinefunction(llm_call_with_tools):
        return await llm_call_with_tools(messages, tools=tools, persona=persona)

    def _invoke():
        return llm_call_with_tools(messages, tools=tools, persona=persona)

    result = await asyncio.to_thread(_invoke)
    if _inspect.isawaitable(result):
        return await result
    return result


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def draft_node(state: MainGraphState, llm_call: Any) -> dict:
    """Generate initial draft response (no tool calling)."""
    system_msg = "You are a helpful assistant."
    draft = await _call_llm_async(
        llm_call,
        system_msg,
        state.get("input_text", ""),
        state.get("persona", ""),
    )
    return {"draft_response": draft}


async def tool_decide_node(
    state: MainGraphState,
    llm_call_with_tools: Any,
    tool_registry: Any,
    persona: Any,
    *,
    speaker_verified: bool = False,
    system_prompt: str = "You are a helpful assistant.",
) -> dict:
    """Ask the LLM whether to call a tool or answer directly.

    On entry, `state["messages"]` accumulates the running conversation
    (system + user + any prior assistant/tool messages). On exit:
    - If LLM emits tool_calls → write them to `pending_tool_calls`, append
      the assistant message to history, leave `draft_response` empty.
    - Otherwise → set `draft_response` to the content, clear pending calls.
    """
    messages = list(state.get("messages") or [])
    if not messages:
        # First decision pass — seed system + user
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state.get("input_text", "")},
        ]

    schemas = tool_registry.schemas_for_persona(persona, speaker_verified=speaker_verified) if tool_registry else None

    response = await _call_llm_with_tools_async(
        llm_call_with_tools,
        messages=messages,
        tools=schemas or None,
        persona=state.get("persona", ""),
    )

    content = response.get("content") or ""
    tool_calls = response.get("tool_calls") or []

    if tool_calls:
        # Append the assistant message that proposes tool calls
        assistant_msg = {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc.get("id") or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                    },
                }
                for i, tc in enumerate(tool_calls)
            ],
        }
        return {
            "messages": messages + [assistant_msg],
            "pending_tool_calls": tool_calls,
            "draft_response": "",
        }

    # Plain answer — no tool needed
    return {
        "messages": messages + [{"role": "assistant", "content": content}],
        "pending_tool_calls": [],
        "draft_response": content,
    }


async def tool_execute_node(
    state: MainGraphState,
    tool_registry: Any,
    *,
    security_guard: Any = None,
) -> dict:
    """Dispatch each pending tool call and append the results to history."""
    pending = state.get("pending_tool_calls") or []
    messages = list(state.get("messages") or [])
    tools_called = list(state.get("tools_called") or [])
    tool_results = list(state.get("tool_results") or [])

    context = {
        "user_id": state.get("user_id", ""),
        "persona": state.get("persona", ""),
        "active_persona_id": state.get("active_persona_id") or state.get("persona", ""),
    }

    for tc in pending:
        name = tc.get("name", "")
        args = tc.get("arguments") or {}
        call_id = tc.get("id") or "call_0"

        result = await tool_registry.dispatch(name, args, context=context)
        result_payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)

        # Wrap external-content tools' output with the security guard so
        # injected data is tagged as untrusted before re-entering the LLM.
        serialized = json.dumps(result_payload, ensure_ascii=False, default=str)
        if security_guard is not None and result_payload.get("ok"):
            try:
                wrapped = security_guard.wrap_external(serialized, source=f"tool:{name}")
                serialized = wrapped.to_xml()
            except Exception as e:  # noqa: BLE001
                logger.debug("guard.wrap_external failed for %s: %r", name, e)

        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": serialized,
        })
        tools_called.append(name)
        tool_results.append({"name": name, "args": args, "result": result_payload})

    return {
        "messages": messages,
        "tools_called": tools_called,
        "tool_results": tool_results,
        "pending_tool_calls": [],
        "tool_iter": (state.get("tool_iter") or 0) + 1,
    }


async def critic_node(
    state: MainGraphState,
    llm_call: Any,
    security_guard: Any = None,
) -> dict:
    """Critique draft for persona consistency and safety.

    If tool calling exited with no draft (e.g. iteration cap reached while
    LLM still wanted to call tools), salvage the last non-empty assistant
    content from message history.
    """
    criticism: list[str] = []
    is_safe = True
    draft = state.get("draft_response", "") or ""
    if not draft:
        for m in reversed(state.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                draft = m["content"]
                break

    if security_guard:
        wrapped = security_guard.wrap_external(draft, source="agent_response")
        if not security_guard.is_safe(wrapped):
            criticism.append("Response contains potential injection patterns")
            is_safe = False

    consistency_prompt = (
        "Evaluate if this response maintains the persona.\n"
        f"PERSONA: {state.get('persona', '')}\n"
        f"RESPONSE: {draft}\n\n"
        'Return JSON only, no extra text: {"consistent": true, "reason": "..."}'
    )

    raw_check = await _call_llm_async(
        llm_call,
        "You are a consistency evaluator. Return only JSON.",
        consistency_prompt,
        state.get("persona", ""),
    )

    import json as _json

    is_consistent = True
    try:
        # Strip markdown code fences if model wraps its JSON
        cleaned = raw_check.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        obj = _json.loads(cleaned)
        is_consistent = bool(obj.get("consistent", True))
    except Exception:
        # Fallback: heuristic word matching (kept for robustness)
        text = raw_check.strip().lower()
        first = text.split(maxsplit=1)[0].rstrip(".,!?:;'\"") if text else ""
        has_positive = "yes" in text or "consistent" in text or "appropriate" in text
        is_consistent = not (first in ("no", "否", "不") and not has_positive)

    if not is_consistent:
        criticism.append("Response breaks persona")

    return {"criticism": criticism, "is_safe": is_safe, "draft_response": draft}


async def respond_node(state: MainGraphState) -> dict:
    """Finalize response preparation."""
    if not state.get("is_safe", True) or state.get("criticism"):
        criticism = state.get("criticism") or []
        return {
            "final_response": (
                f"[Critique detected: {'; '.join(criticism)}] "
                "Original response suppressed for safety."
            )
        }
    return {"final_response": state.get("draft_response", "")}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_main_graph(
    llm_call: Any,
    security_guard: Any = None,
    *,
    tool_registry: Any = None,
    persona: Any = None,
    speaker_verified: bool = False,
    llm_call_with_tools: Any = None,
    system_prompt: str = "You are a helpful assistant.",
) -> Any:
    """Build the orchestrator graph.

    Two operating modes:

    1. Plain mode (`tool_registry is None`): legacy draft → critic → respond.
       Backwards-compatible with existing tests / callers.
    2. Tool-calling mode (`tool_registry` provided): tool_decide → tool_execute
       loop (≤ MAX_TOOL_ITERS rounds) → critic → respond. Requires either
       `llm_call_with_tools` (preferred) or falls back to wrapping `llm_call`.

    `persona` only matters in tool-calling mode (filters which tools the LLM
    sees). `speaker_verified=False` masks `require_speaker_verify` tools.
    """
    if tool_registry is not None:
        ll_tools = llm_call_with_tools or _adapt_plain_to_tools(llm_call)
        if HAS_LANGGRAPH:
            return _build_langgraph_with_tools(
                llm_call, ll_tools, security_guard, tool_registry, persona,
                speaker_verified, system_prompt,
            )
        return _build_fallback_with_tools(
            llm_call, ll_tools, security_guard, tool_registry, persona,
            speaker_verified, system_prompt,
        )

    if HAS_LANGGRAPH:
        return _build_langgraph(llm_call, security_guard)
    return _build_fallback(llm_call, security_guard)


def _adapt_plain_to_tools(llm_call: Any) -> Any:
    """Wrap a plain (system, user, persona) -> str callable so it conforms to
    the tool-aware interface (always returning empty tool_calls).

    Only used when caller asked for tool mode but didn't supply a
    tool-aware callable. Useful for tests with mock LLMs.
    """

    def _adapted(messages: list[dict], tools=None, persona=None):
        system = ""
        user_parts: list[str] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system = m.get("content") or ""
            elif role in ("user", "tool"):
                user_parts.append(m.get("content") or "")
        user_msg = "\n".join(user_parts)
        out = llm_call(system, user_msg, persona)
        return {"content": out, "tool_calls": []}

    return _adapted


# --- legacy plain graph (back-compat) ---


def _build_langgraph(llm_call: Any, security_guard: Any = None) -> Any:
    builder = StateGraph(MainGraphState)

    async def draft_wrapper(state: MainGraphState) -> dict:
        return await draft_node(state, llm_call)

    async def critic_wrapper(state: MainGraphState) -> dict:
        return await critic_node(state, llm_call, security_guard)

    async def respond_wrapper(state: MainGraphState) -> dict:
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
    return {
        "nodes": {
            "draft": lambda state: draft_node(state, llm_call),
            "critic": lambda state: critic_node(state, llm_call, security_guard),
            "respond": lambda state: respond_node(state),
        },
        "edges": [("draft", "critic"), ("critic", "respond")],
        "_langgraph_fallback": True,
        "_mode": "plain",
    }


# --- tool-calling graph ---


def _route_after_decide(state: MainGraphState) -> str:
    if state.get("pending_tool_calls"):
        if (state.get("tool_iter") or 0) >= MAX_TOOL_ITERS:
            return "critic"
        return "tool_execute"
    return "critic"


def _build_langgraph_with_tools(
    llm_call: Any,
    llm_call_with_tools: Any,
    security_guard: Any,
    tool_registry: Any,
    persona: Any,
    speaker_verified: bool,
    system_prompt: str,
) -> Any:
    builder = StateGraph(MainGraphState)

    async def decide_wrapper(state: MainGraphState) -> dict:
        return await tool_decide_node(
            state, llm_call_with_tools, tool_registry, persona,
            speaker_verified=speaker_verified, system_prompt=system_prompt,
        )

    async def execute_wrapper(state: MainGraphState) -> dict:
        return await tool_execute_node(state, tool_registry, security_guard=security_guard)

    async def critic_wrapper(state: MainGraphState) -> dict:
        return await critic_node(state, llm_call, security_guard)

    async def respond_wrapper(state: MainGraphState) -> dict:
        return await respond_node(state)

    builder.add_node("tool_decide", decide_wrapper)
    builder.add_node("tool_execute", execute_wrapper)
    builder.add_node("critic", critic_wrapper)
    builder.add_node("respond", respond_wrapper)

    builder.set_entry_point("tool_decide")
    builder.add_conditional_edges("tool_decide", _route_after_decide, {
        "tool_execute": "tool_execute",
        "critic": "critic",
    })
    builder.add_edge("tool_execute", "tool_decide")
    builder.add_edge("critic", "respond")
    builder.add_edge("respond", END)

    return builder.compile()


def _build_fallback_with_tools(
    llm_call: Any,
    llm_call_with_tools: Any,
    security_guard: Any,
    tool_registry: Any,
    persona: Any,
    speaker_verified: bool,
    system_prompt: str,
) -> dict:
    return {
        "nodes": {
            "tool_decide": lambda state: tool_decide_node(
                state, llm_call_with_tools, tool_registry, persona,
                speaker_verified=speaker_verified, system_prompt=system_prompt,
            ),
            "tool_execute": lambda state: tool_execute_node(
                state, tool_registry, security_guard=security_guard,
            ),
            "critic": lambda state: critic_node(state, llm_call, security_guard),
            "respond": lambda state: respond_node(state),
        },
        "edges": [
            ("tool_decide", "tool_execute"),
            ("tool_execute", "tool_decide"),
            ("tool_decide", "critic"),
            ("critic", "respond"),
        ],
        "_langgraph_fallback": True,
        "_mode": "tools",
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_graph(
    graph: Any,
    input_text: str,
    persona: str,
    user_id: str = "owner",
    trace_id: str = "",
    active_persona_id: str = "",
) -> MainGraphState:
    """Execute graph on input."""
    state = make_initial_state(
        input_text=input_text,
        persona=persona,
        active_persona_id=active_persona_id or persona,
        user_id=user_id,
        trace_id=trace_id,
    )

    # Compiled LangGraph
    if HAS_LANGGRAPH and not isinstance(graph, dict):
        result = await graph.ainvoke(state)
        return result  # LangGraph already returns MainGraphState (dict)

    # Dict-based fallback
    nodes = graph.get("nodes", {})
    mode = graph.get("_mode", "plain")

    def _merge(s: MainGraphState, patch: Any) -> MainGraphState:
        if not patch:
            return s
        merged = dict(s)
        merged.update(patch)
        return merged  # type: ignore[return-value]

    if mode == "plain":
        for step in ("draft", "critic", "respond"):
            if step in nodes:
                state = _merge(state, await nodes[step](state))
        return state

    # tool-calling mode
    for _ in range(MAX_TOOL_ITERS + 1):
        state = _merge(state, await nodes["tool_decide"](state))
        if not state.get("pending_tool_calls"):
            break
        if (state.get("tool_iter") or 0) >= MAX_TOOL_ITERS:
            break
        state = _merge(state, await nodes["tool_execute"](state))

    state = _merge(state, await nodes["critic"](state))
    state = _merge(state, await nodes["respond"](state))
    return state
