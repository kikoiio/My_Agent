from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.memory.store import MemoryStore

from backend.proactive.triggers import check_emotion_trend, check_topic_followup
from core.types import ProactiveEvent

__all__ = ["proactive_scan"]

logger = logging.getLogger(__name__)

DEFAULT_TRACKED_TOPICS: list[str] = [
    "工作", "面试", "健康", "感情", "项目", "考试",
]


async def proactive_scan(
    store: "MemoryStore",
    user_id: str,
    persona: str,
    tracked_topics: list[str] = DEFAULT_TRACKED_TOPICS,
) -> list[ProactiveEvent]:
    """Return all pending proactive events, sorted by priority (highest first).

    Called every 5 minutes by the Docker proactive service.
    Home-arrival events are not polled here — they fire via FaceGate callback.
    """
    events: list[ProactiveEvent] = []

    try:
        ev = check_emotion_trend(store, user_id, persona)
        if ev is not None:
            events.append(ev)
    except Exception:
        logger.exception("check_emotion_trend failed")

    try:
        events.extend(check_topic_followup(store, user_id, persona, tracked_topics))
    except Exception:
        logger.exception("check_topic_followup failed")

    events.sort(key=lambda e: e.priority, reverse=True)
    return events
