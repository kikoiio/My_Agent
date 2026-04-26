"""Memory access MCP server (access L1/L2/L3 memory)."""

from __future__ import annotations

from typing import Any

__all__ = ["MemoryServer"]


class MemoryServer:
    """MCP interface to agent memory."""

    def __init__(self, store: Any):  # MemoryStore
        """Initialize memory server.

        Args:
            store: MemoryStore instance
        """
        self.store = store

    async def recall(
        self,
        user_id: str,
        persona: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall memories matching a query.

        Args:
            user_id: User ID
            persona: Persona name
            query: Search query
            limit: Number of results

        Returns:
            List of memory entries
        """
        episodes = self.store.episode_search(user_id, persona, query, limit=limit)
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in episodes
        ]

    async def store(
        self,
        user_id: str,
        persona: str,
        content: str,
        event_type: str = "observation",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store new memory.

        Args:
            user_id: User ID
            persona: Persona name
            content: Memory content
            event_type: Type of event
            metadata: Optional metadata

        Returns:
            Episode ID
        """
        return self.store.episode_add(
            user_id=user_id,
            persona=persona,
            event_type=event_type,
            content=content,
            metadata=metadata,
        )

    async def get_summary(
        self,
        user_id: str,
        persona: str,
    ) -> dict[str, Any]:
        """Get memory summary for user/persona pair."""
        episodes = self.store.episode_list_recent(user_id, persona, limit=50)
        dreams = self.store.dream_list_recent(user_id, persona, limit=10)

        return {
            "user_id": user_id,
            "persona": persona,
            "episode_count": len(episodes),
            "dream_count": len(dreams),
            "recent_episodes": [
                {
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "preview": e.content[:100],
                }
                for e in episodes[:5]
            ],
            "recent_dreams": [
                {
                    "category": d.category,
                    "summary": d.summary[:200],
                    "quality_score": d.quality_score,
                }
                for d in dreams[:3]
            ],
        }
