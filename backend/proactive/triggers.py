from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.memory.store import MemoryStore

from core.types import ProactiveEvent

__all__ = ["check_emotion_trend", "check_topic_followup", "check_home_arrival"]

EMOTION_STREAK_DAYS = 3
TOPIC_STALE_DAYS = 3


def check_emotion_trend(
    store: "MemoryStore",
    user_id: str,
    persona: str,
    streak_required: int = EMOTION_STREAK_DAYS,
) -> ProactiveEvent | None:
    """Fire if the last `streak_required` consecutive days all have negative L3 dreams."""
    entries = store.query_emotion_trend(user_id, persona, days=streak_required + 1)
    today = int(time.time() // 86400)
    negative_days = {int(e.timestamp // 86400) for e in entries}
    streak = sum(
        1 for d in range(today - streak_required + 1, today + 1) if d in negative_days
    )
    if streak >= streak_required:
        return ProactiveEvent(
            trigger="emotion_trend",
            persona=persona,
            user_id=user_id,
            message="我注意到你最近好像有些不开心，想聊聊吗？",
            priority=3,
            metadata={"streak_days": streak},
        )
    return None


def check_topic_followup(
    store: "MemoryStore",
    user_id: str,
    persona: str,
    tracked_topics: list[str],
    stale_after_days: int = TOPIC_STALE_DAYS,
) -> list[ProactiveEvent]:
    """Fire for each tracked topic not mentioned in the last `stale_after_days` days."""
    events: list[ProactiveEvent] = []
    for topic in tracked_topics:
        try:
            results = store.episode_search(user_id, persona, topic, limit=1)
        except Exception:
            continue
        if not results:
            continue
        days_ago = (time.time() - results[0].timestamp) / 86400
        if days_ago >= stale_after_days:
            events.append(
                ProactiveEvent(
                    trigger="topic_followup",
                    persona=persona,
                    user_id=user_id,
                    message=f'上次你提到了"{topic}"，现在怎么样了？',
                    priority=2,
                    metadata={"topic": topic, "last_seen_days": round(days_ago, 1)},
                )
            )
    return events


def check_home_arrival(
    confidence: float,
    user_id: str,
    persona: str,
    confidence_threshold: float = 0.8,
) -> ProactiveEvent | None:
    """Fire when face gate verifies owner with sufficient confidence."""
    if confidence >= confidence_threshold:
        return ProactiveEvent(
            trigger="home_arrival",
            persona=persona,
            user_id=user_id,
            message="欢迎回来！今天怎么样？",
            priority=3,
            metadata={"confidence": confidence},
        )
    return None
