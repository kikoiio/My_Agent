"""Bocha web search integration."""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["BochaSearchServer"]

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.bocha.ai/v1"


class BochaSearchServer:
    """Bocha search service integration."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search the web using Bocha."""
        if not self.api_key:
            return []
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_BASE_URL}/web/search",
                    headers=self._headers(),
                    json={"query": query, "count": limit, "freshness": "noLimit"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            pages = (data.get("webPages") or {}).get("value") or []
            return [
                {
                    "title": item.get("name", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in pages[:limit]
            ]
        except Exception as e:
            logger.warning(f"bocha search({query!r}) failed: {e!r}")
            return []

    async def search_news(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search news using Bocha (freshness=Day)."""
        if not self.api_key:
            return []
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_BASE_URL}/web/search",
                    headers=self._headers(),
                    json={"query": query, "count": limit, "freshness": "Day"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            pages = (data.get("webPages") or {}).get("value") or []
            return [
                {
                    "title": item.get("name", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in pages[:limit]
            ]
        except Exception as e:
            logger.warning(f"bocha search_news({query!r}) failed: {e!r}")
            return []

    async def search_images(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search images using Bocha."""
        if not self.api_key:
            return []
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_BASE_URL}/image/search",
                    headers=self._headers(),
                    json={"query": query, "count": limit},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            items = data.get("value") or []
            return [
                {
                    "title": item.get("name", ""),
                    "url": item.get("contentUrl", ""),
                    "thumbnail": item.get("thumbnailUrl", ""),
                }
                for item in items[:limit]
            ]
        except Exception as e:
            logger.warning(f"bocha search_images({query!r}) failed: {e!r}")
            return []
