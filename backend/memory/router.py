"""Memory routing: decide whether content goes to L2 (per-persona) or L3 (shared).

L2 episodic: per-persona private memory (conversation details, private moments)
L3 semantic:  global shared memory (emotions, events, preferences across all personas)
"""

from __future__ import annotations

from typing import Literal

# 触发 L3 共享写入的关键词 — 跨人格都值得知道的信息
SHARED_KEYWORDS: tuple[str, ...] = (
    "情绪", "感受", "心情", "情感",
    "事件", "发生了", "经历",
    "偏好", "喜欢", "讨厌", "习惯",
    "决定", "打算", "计划",
    "关系", "朋友", "家人",
)


def route_memory(content: str, current_persona_id: str) -> Literal["L2", "L3"]:  # noqa: ARG001
    """Return 'L3' if content contains shared keywords, else 'L2'.

    L3 goes to global semantic store (all personas can recall it).
    L2 stays in per-persona episodic store (private to this persona).
    """
    for kw in SHARED_KEYWORDS:
        if kw in content:
            return "L3"
    return "L2"


def should_consolidate(episode_count: int, threshold: int = 50) -> bool:
    """Return True when enough L2 episodes have accumulated to trigger L3 dream consolidation."""
    return episode_count >= threshold
