"""Dream async worker for memory consolidation.

Per plan.md §7.3:
- Triggers on idle (30min), pending (>20 low-quality), cron (03:00 daily)
- Cheap LLM extraction: {preferences, events, habits, relationships, todos}
- Per-(user,persona) asyncio.Lock to prevent concurrent consolidation
- Quality gate before commit
- Privacy regex filtering
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

__all__ = ["DreamWorker"]

logger = logging.getLogger(__name__)


class DreamWorker:
    """Async worker for memory consolidation (L2 → L3)."""

    # Privacy patterns to redact from dreams
    PRIVACY_PATTERNS = [
        r"\b(?:\d{3}-\d{2}-\d{4}|[0-9]{3}-[0-9]{2}-[0-9]{4})\b",  # SSN
        r"\b(?:\d{16}|\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b",  # Credit card
        r"\b[A-Z0-9]{9,}\b",  # API keys / tokens (rough heuristic)
    ]

    def __init__(
        self,
        store: Any,  # MemoryStore
        llm_call_func: Any,  # Callable[[str, str, str] -> str] - (system, user_msg, persona)
        cheap_model: str = "gpt-3.5-turbo",
        min_episodes_per_dream: int = 5,
        quality_threshold: float = 0.7,
    ):
        """Initialize dream worker.

        Args:
            store: MemoryStore instance
            llm_call_func: Callable to invoke cheap LLM for extraction
            cheap_model: LLM model for consolidation
            min_episodes_per_dream: Min episodes to consolidate
            quality_threshold: Min quality score for committed dreams
        """
        self.store = store
        self.llm_call_func = llm_call_func
        self.cheap_model = cheap_model
        self.min_episodes_per_dream = min_episodes_per_dream
        self.quality_threshold = quality_threshold

        # Per-(user_id, persona) locks to serialize consolidation
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def _get_lock(self, user_id: str, persona: str) -> asyncio.Lock:
        """Get or create lock for (user_id, persona) pair."""
        key = (user_id, persona)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _redact_privacy(self, text: str) -> str:
        """Redact sensitive data from text."""
        result = text
        for pattern in self.PRIVACY_PATTERNS:
            result = re.sub(pattern, "[REDACTED]", result)
        return result

    async def consolidate(
        self,
        user_id: str,
        persona: str,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Consolidate recent episodes into dreams.

        Args:
            user_id: User ID
            persona: Persona name
            force: Force consolidation even if conditions not met

        Returns:
            List of created dream dicts with {id, category, summary, quality_score}
        """
        lock = await self._get_lock(user_id, persona)

        async with lock:
            # Get recent episodes (raw material for dreams)
            recent = self.store.episode_list_recent(user_id, persona, limit=100)

            if len(recent) < self.min_episodes_per_dream and not force:
                logger.debug(
                    f"Not enough episodes for {user_id}:{persona} "
                    f"({len(recent)}<{self.min_episodes_per_dream})"
                )
                return []

            # Group by event type
            by_type: dict[str, list[str]] = {}
            for ep in recent:
                if ep.event_type not in by_type:
                    by_type[ep.event_type] = []
                by_type[ep.event_type].append(ep.content)

            # Extract structured dreams via LLM
            dreams_created = []

            for category in ["preferences", "events", "habits", "relationships", "todos"]:
                # Prepare context for extraction
                relevant_content = "\n".join(by_type.get("conversation", [])[:10])
                if not relevant_content:
                    continue

                # Privacy-redact before sending to LLM
                safe_content = self._redact_privacy(relevant_content)

                # Call cheap LLM for extraction
                system_msg = f"""You are extracting {category} from a conversation history.
Extract key {category} as a concise JSON list. Be brief. Return ONLY valid JSON."""
                user_msg = f"Extract {category}:\n{safe_content[:2000]}"

                try:
                    llm_response = await asyncio.to_thread(
                        self.llm_call_func, system_msg, user_msg, persona
                    )
                except Exception as e:
                    logger.warning(f"LLM extraction failed for {category}: {e}")
                    continue

                # Parse LLM response
                try:
                    extracted = json.loads(llm_response)
                    if not isinstance(extracted, (list, dict)):
                        extracted = [llm_response]
                except json.JSONDecodeError:
                    extracted = [llm_response]

                # Create dream entry
                summary = json.dumps(extracted) if isinstance(extracted, (list, dict)) else str(extracted)
                source_ids = [e.id for e in recent[:20]]

                # Quality gate: score based on extraction confidence
                quality_score = self._estimate_quality(llm_response, category)

                if quality_score >= self.quality_threshold:
                    dream_id = self.store.dream_add(
                        user_id,
                        persona,
                        category,
                        summary,
                        source_episode_ids=source_ids,
                        quality_score=quality_score,
                    )
                    dreams_created.append(
                        {
                            "id": dream_id,
                            "category": category,
                            "summary": summary,
                            "quality_score": quality_score,
                        }
                    )
                    logger.info(f"Dream {dream_id} created: {category} (score={quality_score:.2f})")

            return dreams_created

    def _estimate_quality(self, llm_response: str, category: str) -> float:
        """Estimate quality of extracted dream (0.0-1.0).

        Simple heuristic: valid JSON, non-empty, category keywords present.
        """
        score = 0.5  # Base score

        # Check for valid JSON structure
        try:
            data = json.loads(llm_response)
            if isinstance(data, list) and len(data) > 0:
                score += 0.3
            elif isinstance(data, dict) and len(data) > 0:
                score += 0.3
        except json.JSONDecodeError:
            pass

        # Check for category keywords
        lower_response = llm_response.lower()
        category_keywords = {
            "preferences": ["like", "prefer", "want", "love"],
            "events": ["happened", "occurred", "did", "when"],
            "habits": ["usually", "often", "always", "routine", "daily"],
            "relationships": ["friend", "family", "person", "with", "know"],
            "todos": ["need", "should", "todo", "task", "goal", "want"],
        }
        if category in category_keywords:
            for kw in category_keywords[category]:
                if kw in lower_response:
                    score += 0.1
                    break

        return min(1.0, score)

    async def should_consolidate_pending(
        self,
        user_id: str,
        persona: str,
        threshold: int = 20,
    ) -> bool:
        """Check if pending low-quality dreams exceed threshold."""
        pending_count = self.store.dream_count_pending(user_id, persona, min_quality=0.7)
        return pending_count >= threshold

    async def refine_dream(
        self,
        dream_id: int,
        new_summary: str | None = None,
        new_quality_score: float | None = None,
    ) -> None:
        """Manually refine a dream (used by calibration feedback loop)."""
        if new_quality_score is not None:
            self.store.dream_update_quality(dream_id, new_quality_score)
            logger.info(f"Dream {dream_id} quality updated to {new_quality_score:.2f}")
