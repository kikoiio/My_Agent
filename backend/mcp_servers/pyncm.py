"""Netease Cloud Music MCP server (via pyncm)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

__all__ = ["PyncmServer"]

logger = logging.getLogger(__name__)


class PyncmServer:
    """Netease Cloud Music integration.

    Session is produced by `scripts/pyncm_login.py` (phone + password →
    pyncm.LoginViaCellphone → session.dump() JSON).
    """

    def __init__(self, credential_file: str | None = None):
        """Initialize Pyncm server.

        Args:
            credential_file: Path to JSON pyncm session dump. None → unauthenticated.
        """
        self.credential_file = credential_file
        self._session_loaded = False

        if credential_file:
            try:
                self._load_session(credential_file)
                self._session_loaded = True
            except Exception as e:
                logger.warning(f"Failed to load pyncm session from {credential_file}: {e}")

        self.authenticated = self._session_loaded

    @staticmethod
    def _load_session(path: str) -> None:
        """Restore pyncm session from JSON dump.

        pyncm 1.8+ 提供两套序列化：DumpSessionAsString/LoadSessionFromString 走
        "PYNCM"+base64(zlib(...)) 格式；而 Session.dump()/Session.load() 走
        裸 dict。我们的脚本写的是后者（人类可读 JSON），所以这里也用后者。
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        from pyncm import Session, SetCurrentSession
        session = Session()
        session.load(data)
        SetCurrentSession(session)

    async def search_track(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search NCM for tracks. stype=1 = single track."""
        if not self.authenticated:
            return []

        try:
            from pyncm.apis.cloudsearch import GetSearchResult
            result = GetSearchResult(query, stype=1, limit=limit)
            songs = (result.get("result") or {}).get("songs", [])
            return [
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "artist": ", ".join(a.get("name", "") for a in s.get("ar", [])),
                    "album": (s.get("al") or {}).get("name", ""),
                }
                for s in songs[:limit]
            ]
        except Exception as e:
            logger.warning(f"search_track({query!r}) failed: {e!r}")
            return []

    async def get_playlist(self, playlist_id: int) -> dict[str, Any]:
        """Fetch playlist details with track list."""
        if not self.authenticated:
            return {}

        try:
            from pyncm.apis.playlist import GetPlaylistInfo
            data = GetPlaylistInfo(playlist_id)
            playlist = data.get("playlist") or {}
            return {
                "id": playlist.get("id", playlist_id),
                "name": playlist.get("name", ""),
                "tracks": [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "artist": ", ".join(a.get("name", "") for a in t.get("ar", [])),
                    }
                    for t in (playlist.get("tracks") or [])
                ],
            }
        except Exception as e:
            logger.warning(f"get_playlist({playlist_id}) failed: {e!r}")
            return {}

    async def get_user_playlists(self, user_id: int) -> list[dict[str, Any]]:
        """List a user's playlists."""
        if not self.authenticated:
            return []

        try:
            from pyncm.apis.user import GetUserPlaylists
            data = GetUserPlaylists(user_id)
            return [
                {"id": p.get("id"), "name": p.get("name"), "track_count": p.get("trackCount", 0)}
                for p in (data.get("playlist") or [])
            ]
        except Exception as e:
            logger.warning(f"get_user_playlists({user_id}) failed: {e!r}")
            return []

    async def play_track(self, track_id: int) -> bool:
        """Marker for downstream audio pipeline — actual playback is out of scope."""
        return self.authenticated
