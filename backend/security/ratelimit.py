"""Rate limiting with atomic SQL operations.

Per plan.md §8.7: Sliding window or fixed window rate limiting using SQLite.
Atomic operation: UPDATE returns 0 rows if limit exceeded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["RateLimitMode", "RateLimitConfig", "RateLimiter"]


class RateLimitMode(str, Enum):
    """Rate limiting strategy."""

    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    mode: RateLimitMode = RateLimitMode.FIXED_WINDOW
    window_size_seconds: int = 60
    max_requests: int = 100
    per_key: bool = True  # Per-user or global


class RateLimiter:
    """Atomic rate limiter using tracer's SQLite backend."""

    def __init__(
        self,
        tracer: Any,
        config: RateLimitConfig | None = None,
    ):
        """Initialize rate limiter.

        Args:
            tracer: Tracer instance with ratelimit_check method
            config: Rate limit configuration
        """
        self.tracer = tracer
        self.config = config or RateLimitConfig()

    def check(self, key: str) -> bool:
        """Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (e.g., "user:12345", "ip:192.168.1.1")

        Returns:
            True if allowed, False if rate limited
        """
        window_start = self._get_window_start()
        return self.tracer.ratelimit_check(
            key=key,
            limit=self.config.max_requests,
            window_start=window_start,
        )

    def _get_window_start(self) -> float:
        """Get current window start timestamp."""
        if self.config.mode == RateLimitMode.FIXED_WINDOW:
            # Fixed window: round down to window boundary
            now = time.time()
            return now - (now % self.config.window_size_seconds)
        else:
            # Sliding window: use fixed start, tracer manages expiry
            now = time.time()
            return now - self.config.window_size_seconds

    def get_status(self, key: str) -> dict[str, Any]:
        """Get rate limit status for a key."""
        window_start = self._get_window_start()
        count = self.tracer.ratelimit_get_count(key, window_start)
        limit = self.config.max_requests
        remaining = max(0, limit - count)

        return {
            "key": key,
            "count": count,
            "limit": limit,
            "remaining": remaining,
            "window_size_seconds": self.config.window_size_seconds,
            "allowed": remaining > 0,
        }

    def reset(self, key: str) -> None:
        """Reset rate limit counter for a key (admin operation)."""
        window_start = self._get_window_start()
        self.tracer.ratelimit_reset_window(key, window_start)


class ThrottledCall:
    """Context manager for rate-limited function calls."""

    def __init__(self, limiter: RateLimiter, key: str):
        """Initialize throttled call context.

        Args:
            limiter: RateLimiter instance
            key: Rate limit key
        """
        self.limiter = limiter
        self.key = key
        self.allowed = False

    def __enter__(self) -> ThrottledCall:
        """Check rate limit on entry."""
        self.allowed = self.limiter.check(self.key)
        if not self.allowed:
            raise RateLimitExceeded(
                f"Rate limit exceeded for key: {self.key}",
                status=self.limiter.get_status(self.key),
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context (no cleanup needed for atomic model)."""
        pass


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, status: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status or {}
