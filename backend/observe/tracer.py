"""Tracer for observability: SQLite-backed trace storage with judge bank & rate limiting.

Per plan.md §8.5:
- 5 SQLite tables: traces, spans, events, judge_bank, rate_counters
- Atomic operations for rate limiting and state management
- Fast indexing on (persona, user_id, timestamp)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

__all__ = ["Tracer"]


@dataclass
class Trace:
    """Single execution trace."""

    trace_id: str
    persona: str
    user_id: str
    session_id: str
    timestamp: float
    role: str  # "chat", "dream", "memory_writer"
    input_messages_count: int
    output_tokens: int
    error: str | None = None


@dataclass
class Span:
    """Nested span (subtask) within a trace."""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str  # "route", "llm_call", "tool_call", "dream_consolidation"
    timestamp: float
    duration_ms: int
    error: str | None = None


@dataclass
class Event:
    """Single event within a span (e.g., token checkpoint, security gate)."""

    event_id: str
    span_id: str
    trace_id: str
    event_type: str  # "token_checkpoint", "security_gate", "rate_limit", "tool_invoke"
    timestamp: float
    metadata_json: str | None = None


@dataclass
class JudgeBank:
    """Judge verdict for a specific trace."""

    trace_id: str
    judge_id: str  # e.g., "gpt4", "claude3", "ensemble"
    score: float  # 0.0 - 1.0
    verdict: str  # "pass", "fail", "uncertain"
    reasoning: str | None = None
    created_at: float = None


class Tracer:
    """SQLite-backed tracer for observability."""

    def __init__(self, db_path: Path | str = "data/trace.db"):
        """Initialize tracer. Creates DB if missing."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create or verify DB schema."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                -- Traces: top-level execution records
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    persona TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    role TEXT NOT NULL,
                    input_messages_count INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    error TEXT,
                    created_at REAL NOT NULL
                );

                -- Spans: nested subtasks
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(trace_id) REFERENCES traces(trace_id),
                    FOREIGN KEY(parent_span_id) REFERENCES spans(span_id)
                );

                -- Events: atomic actions within spans
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    span_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata_json TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(span_id) REFERENCES spans(span_id),
                    FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
                );

                -- Judge bank: verdicts on traces from different judges
                CREATE TABLE IF NOT EXISTS judge_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    judge_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    verdict TEXT NOT NULL,
                    reasoning TEXT,
                    created_at REAL NOT NULL,
                    UNIQUE(trace_id, judge_id),
                    FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
                );

                -- Rate counters: atomic rate limiting
                CREATE TABLE IF NOT EXISTS rate_counters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    window_start REAL NOT NULL,
                    count INTEGER DEFAULT 0,
                    limit_per_window INTEGER DEFAULT 100,
                    UNIQUE(key, window_start)
                );

                -- Indices
                CREATE INDEX IF NOT EXISTS idx_traces_persona_user_ts
                    ON traces(persona, user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_traces_role
                    ON traces(role);
                CREATE INDEX IF NOT EXISTS idx_spans_trace_id
                    ON spans(trace_id);
                CREATE INDEX IF NOT EXISTS idx_events_span_id
                    ON events(span_id);
                CREATE INDEX IF NOT EXISTS idx_events_trace_id
                    ON events(trace_id);
                CREATE INDEX IF NOT EXISTS idx_judge_trace_id
                    ON judge_bank(trace_id);
                """
            )

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-safe DB connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ============ Trace Methods ============

    def trace_add(
        self,
        trace_id: str,
        persona: str,
        user_id: str,
        session_id: str,
        role: str,
        input_messages_count: int = 0,
    ) -> None:
        """Record a new trace."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO traces
                    (trace_id, persona, user_id, session_id, timestamp, role,
                     input_messages_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (trace_id, persona, user_id, session_id, now, role, input_messages_count, now),
                )
                conn.commit()

    def trace_update_tokens(self, trace_id: str, output_tokens: int) -> None:
        """Update token count for a trace."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE traces SET output_tokens=? WHERE trace_id=?",
                    (output_tokens, trace_id),
                )
                conn.commit()

    def trace_set_error(self, trace_id: str, error: str) -> None:
        """Mark trace as failed with error message."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE traces SET error=? WHERE trace_id=?",
                    (error, trace_id),
                )
                conn.commit()

    def trace_get(self, trace_id: str) -> Trace | None:
        """Retrieve trace by ID."""
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM traces WHERE trace_id=?", (trace_id,)
                ).fetchone()
                if row:
                    return Trace(
                        trace_id=row["trace_id"],
                        persona=row["persona"],
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                        timestamp=row["timestamp"],
                        role=row["role"],
                        input_messages_count=row["input_messages_count"],
                        output_tokens=row["output_tokens"],
                        error=row["error"],
                    )
        return None

    def trace_list_recent(
        self,
        persona: str,
        user_id: str,
        limit: int = 100,
        role: str | None = None,
    ) -> list[Trace]:
        """List recent traces for a persona/user."""
        with self._lock:
            with self._get_connection() as conn:
                if role:
                    rows = conn.execute(
                        """
                        SELECT * FROM traces
                        WHERE persona=? AND user_id=? AND role=?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (persona, user_id, role, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM traces
                        WHERE persona=? AND user_id=?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (persona, user_id, limit),
                    ).fetchall()

                return [
                    Trace(
                        trace_id=row["trace_id"],
                        persona=row["persona"],
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                        timestamp=row["timestamp"],
                        role=row["role"],
                        input_messages_count=row["input_messages_count"],
                        output_tokens=row["output_tokens"],
                        error=row["error"],
                    )
                    for row in rows
                ]

    # ============ Span Methods ============

    def span_add(
        self,
        span_id: str,
        trace_id: str,
        name: str,
        parent_span_id: str | None = None,
    ) -> None:
        """Record start of a span. Use span_end to record duration."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO spans (span_id, trace_id, parent_span_id, name, timestamp,
                                       duration_ms, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (span_id, trace_id, parent_span_id, name, now, 0, now),
                )
                conn.commit()

    def span_end(self, span_id: str, duration_ms: int, error: str | None = None) -> None:
        """Update span with duration and optional error."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE spans SET duration_ms=?, error=? WHERE span_id=?",
                    (duration_ms, error, span_id),
                )
                conn.commit()

    # ============ Event Methods ============

    def event_add(
        self,
        event_id: str,
        span_id: str,
        trace_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an event within a span."""
        now = datetime.now(timezone.utc).timestamp()
        metadata_json = json.dumps(metadata) if metadata else None
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO events (event_id, span_id, trace_id, event_type,
                                       timestamp, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, span_id, trace_id, event_type, now, metadata_json, now),
                )
                conn.commit()

    # ============ Judge Bank Methods ============

    def judge_add(
        self,
        trace_id: str,
        judge_id: str,
        score: float,
        verdict: str,
        reasoning: str | None = None,
    ) -> None:
        """Record judge verdict for a trace."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO judge_bank
                    (trace_id, judge_id, score, verdict, reasoning, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (trace_id, judge_id, score, verdict, reasoning, now),
                )
                conn.commit()

    def judge_get_verdicts(self, trace_id: str) -> list[JudgeBank]:
        """Get all judge verdicts for a trace."""
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT trace_id, judge_id, score, verdict, reasoning, created_at
                    FROM judge_bank
                    WHERE trace_id=?
                    ORDER BY created_at DESC
                    """,
                    (trace_id,),
                ).fetchall()

                return [
                    JudgeBank(
                        trace_id=row["trace_id"],
                        judge_id=row["judge_id"],
                        score=row["score"],
                        verdict=row["verdict"],
                        reasoning=row["reasoning"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]

    # ============ Rate Limiting (Atomic) ============

    def ratelimit_check(
        self,
        key: str,
        limit: int,
        window_start: float,
    ) -> bool:
        """Check if rate limit exceeded. Returns True if allowed, False if exceeded.

        Atomic operation: increments counter only if below limit.
        """
        with self._lock:
            with self._get_connection() as conn:
                # Try to increment counter if below limit
                cursor = conn.execute(
                    """
                    UPDATE rate_counters SET count = count + 1
                    WHERE key=? AND window_start=? AND count < ?
                    """,
                    (key, window_start, limit),
                )
                affected = cursor.rowcount

                if affected == 0:
                    # No existing counter or already at limit; try insert
                    try:
                        conn.execute(
                            """
                            INSERT INTO rate_counters (key, window_start, count, limit_per_window)
                            VALUES (?, ?, 1, ?)
                            """,
                            (key, window_start, limit),
                        )
                        affected = 1
                    except sqlite3.IntegrityError:
                        # Concurrent insert; check again
                        row = conn.execute(
                            "SELECT count FROM rate_counters WHERE key=? AND window_start=?",
                            (key, window_start),
                        ).fetchone()
                        affected = 1 if (row and row[0] < limit) else 0

                conn.commit()
                return affected > 0

    def ratelimit_get_count(self, key: str, window_start: float) -> int:
        """Get current count in a rate limit window."""
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT count FROM rate_counters WHERE key=? AND window_start=?",
                    (key, window_start),
                ).fetchone()
                return row[0] if row else 0

    def ratelimit_reset_window(self, key: str, window_start: float) -> None:
        """Reset rate limit counter for a window."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM rate_counters WHERE key=? AND window_start=?",
                    (key, window_start),
                )
                conn.commit()
