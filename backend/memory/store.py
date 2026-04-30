"""Memory store: SQLite L1 (session) + FTS5 L2 (episodic) + L3 (dreams).

Per plan.md §7.2:
- L1: Session memory (12K tokens max per persona), recent turns
- L2: Episodic memory (FTS5 indexed for semantic search)
- L3: Dream memory (async consolidation, long-term patterns)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

__all__ = ["MemoryStore"]


@dataclass
class SessionMemory:
    """L1: Session memory for current conversation turn."""

    user_id: str
    persona: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    context_tokens: int = 0
    max_tokens: int = 12000

    def can_add(self, text: str, est_tokens: int = 100) -> bool:
        """Check if adding text would exceed token budget."""
        return self.context_tokens + est_tokens <= self.max_tokens


@dataclass
class EpisodeEntry:
    """L2: Single episodic memory entry (searchable)."""

    id: int
    user_id: str
    persona: str
    timestamp: float
    event_type: str  # "conversation", "action", "observation", "memory_consolidation"
    content: str
    embedding_vector: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DreamEntry:
    """L3: Dream (consolidated memory pattern)."""

    id: int
    user_id: str
    persona: str
    timestamp: float
    category: str  # "preferences", "events", "habits", "relationships", "todos"
    summary: str
    source_episode_ids: list[int] = field(default_factory=list)
    quality_score: float = 0.0


class MemoryStore:
    """SQLite-backed memory store with 3 tiers."""

    def __init__(self, db_path: Path | str = "data/memory.db"):
        """Initialize memory store. Creates DB if missing."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create or verify DB schema."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                -- L1: Session memory (simplified in this store; mainly transient in AgentState)
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    token_usage INTEGER DEFAULT 0,
                    UNIQUE(user_id, persona)
                );

                -- L2: Episodic memory with FTS5
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at REAL NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    content,
                    event_type,
                    metadata_json,
                    content_rowid=id,
                    content=episodes
                );

                -- Triggers to keep FTS5 index in sync with episodes
                CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
                    INSERT INTO episodes_fts(rowid, content, event_type, metadata_json)
                    VALUES (new.id, new.content, new.event_type, new.metadata_json);
                END;
                CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
                    INSERT INTO episodes_fts(episodes_fts, rowid, content, event_type, metadata_json)
                    VALUES ('delete', old.id, old.content, old.event_type, old.metadata_json);
                END;
                CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
                    INSERT INTO episodes_fts(episodes_fts, rowid, content, event_type, metadata_json)
                    VALUES ('delete', old.id, old.content, old.event_type, old.metadata_json);
                    INSERT INTO episodes_fts(rowid, content, event_type, metadata_json)
                    VALUES (new.id, new.content, new.event_type, new.metadata_json);
                END;

                -- L3: Dreams (consolidated patterns)
                CREATE TABLE IF NOT EXISTS dreams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source_episode_ids_json TEXT,
                    quality_score REAL DEFAULT 0.0,
                    created_at REAL NOT NULL
                );

                -- Indices for common queries
                CREATE INDEX IF NOT EXISTS idx_episodes_user_persona
                    ON episodes(user_id, persona, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_episodes_type
                    ON episodes(event_type);
                CREATE INDEX IF NOT EXISTS idx_dreams_user_persona
                    ON dreams(user_id, persona, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_dreams_category
                    ON dreams(category);
                """
            )

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-safe DB connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ============ Session (L1) Methods ============

    def session_init(self, user_id: str, persona: str) -> None:
        """Initialize or touch session entry."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (user_id, persona, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, persona) DO UPDATE SET updated_at = ?
                    """,
                    (user_id, persona, now, now, now),
                )
                conn.commit()

    def session_get_token_usage(self, user_id: str, persona: str) -> int:
        """Get current session token usage."""
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT token_usage FROM sessions WHERE user_id=? AND persona=?",
                    (user_id, persona),
                ).fetchone()
                return row[0] if row else 0

    def session_add_tokens(self, user_id: str, persona: str, count: int) -> None:
        """Add tokens to session usage counter."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE sessions SET token_usage = token_usage + ?
                    WHERE user_id=? AND persona=?
                    """,
                    (count, user_id, persona),
                )
                conn.commit()

    # ============ Episode (L2) Methods ============

    def episode_add(
        self,
        user_id: str,
        persona: str,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Add episodic memory entry. Returns entry ID."""
        now = datetime.now(timezone.utc).timestamp()
        metadata = metadata or {}
        metadata_json = json.dumps(metadata)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO episodes
                    (user_id, persona, timestamp, event_type, content, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, persona, now, event_type, content, metadata_json, now),
                )
                episode_id = cursor.lastrowid
                conn.commit()
        return episode_id

    def episode_search(
        self,
        user_id: str,
        persona: str,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> list[EpisodeEntry]:
        """Full-text search episodes using FTS5."""
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT e.id, e.user_id, e.persona, e.timestamp, e.event_type,
                           e.content, e.metadata_json
                    FROM episodes e
                    WHERE e.user_id=? AND e.persona=?
                    AND e.id IN (
                        SELECT rowid FROM episodes_fts
                        WHERE episodes_fts MATCH ?
                    )
                    ORDER BY e.timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, persona, query, limit, offset),
                ).fetchall()

                return [
                    EpisodeEntry(
                        id=row[0],
                        user_id=row[1],
                        persona=row[2],
                        timestamp=row[3],
                        event_type=row[4],
                        content=row[5],
                        metadata=json.loads(row[6]) if row[6] else {},
                    )
                    for row in rows
                ]

    def episode_list_recent(
        self,
        user_id: str,
        persona: str,
        limit: int = 20,
        event_type: str | None = None,
    ) -> list[EpisodeEntry]:
        """Get recent episodic memories."""
        with self._lock:
            with self._get_connection() as conn:
                if event_type:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, persona, timestamp, event_type,
                               content, metadata_json
                        FROM episodes
                        WHERE user_id=? AND persona=? AND event_type=?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (user_id, persona, event_type, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, persona, timestamp, event_type,
                               content, metadata_json
                        FROM episodes
                        WHERE user_id=? AND persona=?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (user_id, persona, limit),
                    ).fetchall()

                return [
                    EpisodeEntry(
                        id=row[0],
                        user_id=row[1],
                        persona=row[2],
                        timestamp=row[3],
                        event_type=row[4],
                        content=row[5],
                        metadata=json.loads(row[6]) if row[6] else {},
                    )
                    for row in rows
                ]

    def episode_get_by_id(self, episode_id: int) -> EpisodeEntry | None:
        """Retrieve single episode by ID."""
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT id, user_id, persona, timestamp, event_type,
                           content, metadata_json
                    FROM episodes
                    WHERE id=?
                    """,
                    (episode_id,),
                ).fetchone()

                if row:
                    return EpisodeEntry(
                        id=row[0],
                        user_id=row[1],
                        persona=row[2],
                        timestamp=row[3],
                        event_type=row[4],
                        content=row[5],
                        metadata=json.loads(row[6]) if row[6] else {},
                    )
        return None

    # ============ Dream (L3) Methods ============

    def dream_add(
        self,
        user_id: str,
        persona: str,
        category: str,
        summary: str,
        source_episode_ids: list[int] | None = None,
        quality_score: float = 0.0,
    ) -> int:
        """Add dream (consolidated memory). Returns dream ID."""
        now = datetime.now(timezone.utc).timestamp()
        source_episode_ids = source_episode_ids or []
        source_ids_json = json.dumps(source_episode_ids)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO dreams
                    (user_id, persona, timestamp, category, summary,
                     source_episode_ids_json, quality_score, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, persona, now, category, summary, source_ids_json, quality_score, now),
                )
                dream_id = cursor.lastrowid
                conn.commit()
        return dream_id

    def dream_list_recent(
        self,
        user_id: str,
        persona: str,
        limit: int = 10,
        category: str | None = None,
        min_quality: float = 0.0,
    ) -> list[DreamEntry]:
        """Retrieve recent dreams, optionally filtered by category and quality."""
        with self._lock:
            with self._get_connection() as conn:
                if category:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, persona, timestamp, category,
                               summary, source_episode_ids_json, quality_score
                        FROM dreams
                        WHERE user_id=? AND persona=? AND category=? AND quality_score >= ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (user_id, persona, category, min_quality, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, persona, timestamp, category,
                               summary, source_episode_ids_json, quality_score
                        FROM dreams
                        WHERE user_id=? AND persona=? AND quality_score >= ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (user_id, persona, min_quality, limit),
                    ).fetchall()

                return [
                    DreamEntry(
                        id=row[0],
                        user_id=row[1],
                        persona=row[2],
                        timestamp=row[3],
                        category=row[4],
                        summary=row[5],
                        source_episode_ids=json.loads(row[6]) if row[6] else [],
                        quality_score=row[7],
                    )
                    for row in rows
                ]

    def dream_count_pending(
        self,
        user_id: str,
        persona: str,
        min_quality: float = 0.0,
    ) -> int:
        """Count dreams below quality threshold (candidates for refinement)."""
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM dreams
                    WHERE user_id=? AND persona=? AND quality_score < ?
                    """,
                    (user_id, persona, min_quality),
                ).fetchone()
                return row[0] if row else 0

    def dream_update_quality(self, dream_id: int, new_score: float) -> None:
        """Update quality score of a dream."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE dreams SET quality_score=? WHERE id=?",
                    (new_score, dream_id),
                )
                conn.commit()

    def query_emotion_trend(
        self,
        user_id: str,
        persona: str,
        days: int = 7,
        negative_keywords: tuple[str, ...] = (
            "难过", "焦虑", "沮丧", "不开心", "担心", "压力", "伤心",
            "sad", "anxious", "depressed", "stressed", "unhappy",
        ),
    ) -> list[DreamEntry]:
        """Return L3 dream entries from last N days whose summary contains negative keywords."""
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, user_id, persona, timestamp, category, summary, "
                    "source_episode_ids_json, quality_score FROM dreams "
                    "WHERE user_id=? AND timestamp>=? ORDER BY timestamp DESC",
                    (user_id, cutoff),
                ).fetchall()
        entries = [
            DreamEntry(
                id=row[0],
                user_id=row[1],
                persona=row[2],
                timestamp=row[3],
                category=row[4],
                summary=row[5],
                source_episode_ids=json.loads(row[6] or "[]"),
                quality_score=row[7],
            )
            for row in rows
        ]
        return [e for e in entries if any(kw in e.summary for kw in negative_keywords)]

    # ============ Cleanup Methods ============

    def prune_old_episodes(self, user_id: str, persona: str, keep_hours: int = 720) -> int:
        """Delete episodes older than keep_hours. Returns count deleted."""
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - (keep_hours * 3600)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM episodes
                    WHERE user_id=? AND persona=? AND timestamp<?
                    """,
                    (user_id, persona, cutoff),
                )
                deleted = cursor.rowcount
                conn.commit()
        return deleted

    def export_json(
        self,
        user_id: str,
        persona: str,
        include_episodes: bool = True,
        include_dreams: bool = True,
    ) -> dict[str, Any]:
        """Export all memory for a (user_id, persona) pair as JSON."""
        result: dict[str, Any] = {"user_id": user_id, "persona": persona}

        if include_episodes:
            episodes = self.episode_list_recent(user_id, persona, limit=1000)
            result["episodes"] = [
                {
                    "id": e.id,
                    "timestamp": e.timestamp,
                    "event_type": e.event_type,
                    "content": e.content,
                    "metadata": e.metadata,
                }
                for e in episodes
            ]

        if include_dreams:
            dreams = self.dream_list_recent(user_id, persona, limit=1000)
            result["dreams"] = [
                {
                    "id": d.id,
                    "timestamp": d.timestamp,
                    "category": d.category,
                    "summary": d.summary,
                    "quality_score": d.quality_score,
                    "source_episode_ids": d.source_episode_ids,
                }
                for d in dreams
            ]

        return result
