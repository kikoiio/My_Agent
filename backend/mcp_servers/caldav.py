"""CalDAV calendar integration."""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import caldav

__all__ = ["CalDAVServer", "CalendarEvent"]

VCAL_FMT = "%Y%m%dT%H%M%S"
_thread_pool = ThreadPoolExecutor(max_workers=2)


@dataclass
class CalendarEvent:
    """Calendar event."""

    id: str
    title: str
    description: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str = ""


def _build_vcal(title: str, start: datetime, end: datetime,
                description: str = "", location: str = "") -> str:
    """Build iCalendar VCALENDAR string."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MyAgent//CalDAV//CN",
        "BEGIN:VEVENT",
        f"SUMMARY:{title}",
        f"DTSTART:{start.strftime(VCAL_FMT)}",
        f"DTEND:{end.strftime(VCAL_FMT)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{description}")
    if location:
        lines.append(f"LOCATION:{location}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(lines)


def _parse_vcal(data: str, href: str) -> CalendarEvent | None:
    """Parse iCalendar data into CalendarEvent."""
    try:
        title = ""
        description = ""
        location = ""
        start_time: datetime | None = None
        end_time: datetime | None = None

        for line in data.splitlines():
            line = line.strip()
            if line.startswith("SUMMARY:"):
                title = line[8:]
            elif line.startswith("DESCRIPTION:"):
                description = line[12:]
            elif line.startswith("LOCATION:"):
                location = line[9:]
            elif line.startswith("DTSTART:"):
                val = line[8:].strip()
                try:
                    start_time = datetime.strptime(val, VCAL_FMT)
                except ValueError:
                    pass
            elif line.startswith("DTEND:"):
                val = line[6:].strip()
                try:
                    end_time = datetime.strptime(val, VCAL_FMT)
                except ValueError:
                    pass

        return CalendarEvent(
            id=href or "",
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            location=location,
        )
    except Exception:
        return None


class CalDAVServer:
    """CalDAV calendar server integration."""

    def __init__(self, url: str | None = None,
                 username: str | None = None,
                 password: str | None = None):
        self.url = url
        self.username = username
        self.password = password
        self._client: caldav.DAVClient | None = None

    @property
    def authenticated(self) -> bool:
        return all([self.url, self.username, self.password])

    async def _client_sync(self) -> caldav.DAVClient | None:
        """Get or create the DAVClient (lazy, via executor)."""
        if self._client is not None:
            return self._client
        if not self.authenticated:
            return None
        loop = asyncio.get_running_loop()
        self._client = await loop.run_in_executor(
            _thread_pool,
            lambda: caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password,
            ),
        )
        return self._client

    async def _get_calendars(self) -> list[Any]:
        """Get list of available calendars."""
        client = await self._client_sync()
        if client is None:
            return []
        loop = asyncio.get_running_loop()
        principal = await loop.run_in_executor(_thread_pool, client.principal)
        return await loop.run_in_executor(_thread_pool, principal.calendars)

    async def list_events(
        self,
        calendar_name: str = "default",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[CalendarEvent]:
        """List calendar events."""
        calendars = await self._get_calendars()
        if not calendars:
            return []

        cal = calendars[0]
        if calendar_name != "default":
            for c in calendars:
                name = c.name or ""
                if calendar_name in str(name):
                    cal = c
                    break

        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            _thread_pool,
            lambda: cal.date_search(start=start_date, end=end_date, expand=True),
        )

        result: list[CalendarEvent] = []
        for ev in events:
            parsed = _parse_vcal(ev.data, ev.href)
            if parsed is not None:
                result.append(parsed)
        return result

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        location: str = "",
    ) -> str:
        """Create calendar event. Returns event ID."""
        calendars = await self._get_calendars()
        if not calendars:
            return ""

        vcal = _build_vcal(title, start_time, end_time, description, location)
        loop = asyncio.get_running_loop()
        event = await loop.run_in_executor(
            _thread_pool, lambda: calendars[0].save_event(vcal),
        )
        return event.href or ""

    async def delete_event(self, event_id: str) -> bool:
        """Delete calendar event by ID."""
        calendars = await self._get_calendars()
        if not calendars:
            return False

        loop = asyncio.get_running_loop()
        for cal in calendars:
            events = await loop.run_in_executor(_thread_pool, cal.events)
            for ev in events:
                if ev.href == event_id or event_id in (ev.href or ""):
                    await loop.run_in_executor(_thread_pool, ev.delete)
                    return True
        return False

    async def update_event(self, event_id: str, **kwargs: Any) -> bool:
        """Update calendar event (delete + recreate)."""
        calendars = await self._get_calendars()
        if not calendars:
            return False

        loop = asyncio.get_running_loop()
        for cal in calendars:
            events = await loop.run_in_executor(_thread_pool, cal.events)
            for ev in events:
                if ev.href == event_id or event_id in (ev.href or ""):
                    await loop.run_in_executor(_thread_pool, ev.delete)
                    title = kwargs.get("title", "")
                    start = kwargs.get("start_time", datetime.now())
                    end = kwargs.get("end_time", datetime.now())
                    desc = kwargs.get("description", "")
                    loc = kwargs.get("location", "")
                    vcal = _build_vcal(title, start, end, desc, loc)
                    await loop.run_in_executor(
                        _thread_pool, lambda: cal.save_event(vcal),
                    )
                    return True
        return False
