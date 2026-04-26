from __future__ import annotations

from .types import AgentState

DEFAULT_SMART_KEYWORDS: tuple[str, ...] = ("分析", "对比", "规划", "写报告", "总结")
DEFAULT_LONG_THRESHOLD: int = 200


def route(
    msg: str,
    ctx: AgentState,
    *,
    smart_keywords: tuple[str, ...] = DEFAULT_SMART_KEYWORDS,
    long_threshold: int = DEFAULT_LONG_THRESHOLD,
) -> str:
    if ctx.role in ("dream", "memory_writer"):
        return "cheap"
    if len(msg) > long_threshold or any(k in msg for k in smart_keywords):
        return "default_smart"
    if ctx.has_image:
        return "vision"
    if ctx.is_long_context_consolidation:
        return "long_context"
    return "default_fast"
