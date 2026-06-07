"""Calendar connector (P6) — upcoming events from ICS URL + local reminders."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings
from ..reminders import list_reminders

_ICS_URL = re.compile(r"https?://[^\s]+")


def is_configured() -> bool:
    return bool((settings.calendar_ics_url or "").strip())


async def upcoming(days: int = 7, user_id: int = 0) -> str:
    """Events from external ICS + active reminders."""
    days = max(1, min(days, 30))
    parts: list[str] = []
    if user_id:
        rem = await list_reminders(user_id)
        if rem and "немає" not in rem.lower():
            parts.append("## Нагадування JARVIS\n" + rem)
    if is_configured():
        ics_text = await _fetch_ics(settings.calendar_ics_url.strip())
        events = _parse_ics_events(ics_text, days)
        if events:
            parts.append("## Календар (ICS)\n" + "\n".join(events))
        elif ics_text:
            parts.append("## Календар\nПодій у діапазоні не знайдено.")
    if not parts:
        if not is_configured() and not user_id:
            return "Calendar не налаштовано (CALENDAR_ICS_URL у .env)."
        return "Найближчих подій немає."
    return "\n\n".join(parts)


async def _fetch_ics(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=True) as cli:
            resp = await cli.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError as exc:
        return f"ICS fetch error: {exc}"


def _parse_ics_events(ics: str, days: int) -> list[str]:
    if not ics or ics.startswith("ICS fetch"):
        return []
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    events: list[tuple[datetime, str]] = []
    dtstart: datetime | None = None
    summary = ""
    for line in ics.splitlines():
        line = line.strip()
        if line.startswith("DTSTART"):
            dtstart = _parse_ics_dt(line.split(":", 1)[-1])
        elif line.startswith("SUMMARY:"):
            summary = line[8:].strip()
        elif line == "END:VEVENT" and dtstart is not None:
            if now <= dtstart <= end:
                events.append((dtstart, summary or "Event"))
            dtstart = None
            summary = ""
    events.sort(key=lambda x: x[0])
    return [f"• {dt.strftime('%Y-%m-%d %H:%M')} — {title}" for dt, title in events[:20]]


def _parse_ics_dt(raw: str) -> datetime:
    raw = raw.strip()
    if raw.endswith("Z"):
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" in raw:
        return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.strptime(raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
