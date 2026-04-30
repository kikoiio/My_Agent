"""Docker entrypoint for the proactive awareness scanner.

Runs proactive_scan() once and prints any pending events to stdout.
Called in a loop by the Docker proactive service every 300 seconds.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script (scripts/ is one level below root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.memory.store import MemoryStore
from backend.proactive.scanner import proactive_scan


async def main() -> None:
    store = MemoryStore(os.getenv("MEMORY_DB_PATH", "data/memory.db"))
    user_id = os.getenv("PROACTIVE_USER_ID", "owner")
    persona = os.getenv("PROACTIVE_PERSONA", "assistant")
    events = await proactive_scan(store, user_id, persona)
    for ev in events:
        print(f"[{ev.trigger}] priority={ev.priority} | {ev.message}")
    if not events:
        print("[proactive] no events")


asyncio.run(main())
