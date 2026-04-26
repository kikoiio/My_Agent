from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class BreakerTripped(Exception):
    pass


@dataclass(slots=True)
class CircuitBreaker:
    """Per-run circuit breaker enforcing both step cap and loop detection.

    See plan.md §6.6: a single agent run is capped at `max_steps` tool
    invocations, and any (tool_name, args_hash) repeat trips the breaker.
    Constructed fresh per run; not shared across runs.
    """

    max_steps: int = 15
    seen: set[str] = field(default_factory=set)
    steps: int = 0

    def check(self, tool_name: str, args: dict[str, Any]) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BreakerTripped(f"step limit {self.max_steps} exceeded")
        key = self._key(tool_name, args)
        if key in self.seen:
            raise BreakerTripped(f"duplicate call: {tool_name} with same args")
        self.seen.add(key)

    @staticmethod
    def _key(tool_name: str, args: dict[str, Any]) -> str:
        payload = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{tool_name}:{h}"
