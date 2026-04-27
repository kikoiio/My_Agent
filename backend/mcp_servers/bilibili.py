"""Bilibili live chat / user MCP server."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

__all__ = ["BilibiliServer"]

logger = logging.getLogger(__name__)


class BilibiliServer:
    """Bilibili integration backed by bilibili-api-python.

    Cookies are produced by `scripts/bilibili_cookie_import.py` (reads cookies
    from the user's already-logged-in local browser via browser-cookie3).
    """

    def __init__(self, credential_file: str | None = None):
        """Initialize Bilibili server.

        Args:
            credential_file: Path to JSON cookie file. None → unauthenticated stub.
        """
        self.credential_file = credential_file
        self._credential = None

        if credential_file:
            try:
                self._credential = self._load_credential(credential_file)
                self._register_http_client()
            except Exception as e:
                logger.warning(f"Failed to load bilibili credential from {credential_file}: {e}")

        self.authenticated = self._credential is not None

    @staticmethod
    def _register_http_client() -> None:
        """bilibili-api-python v17+ 需要显式注册 HTTP 客户端。aiohttp 是项目已有依赖。"""
        try:
            import bilibili_api  # type: ignore
        except ImportError:
            return

        for impl in ("aiohttp", "httpx", "curl_cffi"):
            select_client = getattr(bilibili_api, "select_client", None)
            if callable(select_client):
                try:
                    select_client(impl)
                    return
                except Exception:
                    pass

            rs = getattr(bilibili_api, "request_settings", None)
            if rs is not None:
                try:
                    if hasattr(rs, "set_impl"):
                        rs.set_impl(impl)
                        return
                    if hasattr(rs, "set"):
                        rs.set("impl", impl)
                        return
                except Exception:
                    continue

    @staticmethod
    def _load_credential(path: str) -> Any:
        """Load JSON file → bilibili_api.Credential. Lazy import keeps tests light."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        from bilibili_api import Credential
        return Credential(
            sessdata=data["sessdata"],
            bili_jct=data["bili_jct"],
            buvid3=data["buvid3"],
            dedeuserid=data["dedeuserid"],
        )

    async def get_live_chat(self, room_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent messages from a live room.

        bilibili-api-python's LiveDanmaku is a streaming subscriber — for a
        one-shot snapshot we use the historical danmaku endpoint.
        """
        if not self.authenticated:
            return []

        try:
            from bilibili_api import live
            room = live.LiveRoom(room_display_id=room_id, credential=self._credential)
            history = await room.get_chat_msg(number=limit)
            return [
                {
                    "uid": msg.get("uid"),
                    "uname": msg.get("nickname") or msg.get("uname"),
                    "message": msg.get("text", ""),
                    "timestamp": msg.get("timeline_ts") or msg.get("timeline"),
                }
                for msg in (history.get("admin", []) + history.get("room", []))[:limit]
            ]
        except Exception as e:
            logger.warning(f"get_live_chat({room_id}) failed: {e!r}")
            return []

    async def send_message(self, room_id: int, message: str) -> bool:
        """Send a danmaku to the live room."""
        if not self.authenticated:
            return False

        try:
            from bilibili_api import live
            room = live.LiveRoom(room_display_id=room_id, credential=self._credential)
            await room.send_danmaku(live.Danmaku(text=message))
            return True
        except Exception as e:
            logger.warning(f"send_message({room_id}) failed: {e!r}")
            return False

    async def get_room_info(self, room_id: int) -> dict[str, Any]:
        """Get live room metadata."""
        if not self.authenticated:
            return {"room_id": room_id, "title": "", "live_status": 0, "online": 0}

        try:
            from bilibili_api import live
            room = live.LiveRoom(room_display_id=room_id, credential=self._credential)
            info = await room.get_room_info()
            base = info.get("room_info", info)
            return {
                "room_id": base.get("room_id", room_id),
                "title": base.get("title", ""),
                "live_status": base.get("live_status", 0),
                "online": base.get("online", 0),
            }
        except Exception as e:
            logger.warning(f"get_room_info({room_id}) failed: {e!r}")
            return {"room_id": room_id, "title": "", "live_status": 0, "online": 0}
