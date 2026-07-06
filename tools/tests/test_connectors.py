"""P6 connectors."""
import pytest
from app.connectors import calendar, notion, slack


async def test_notion_not_configured():
    assert "не налаштовано" in await notion.search("q")


async def test_slack_not_configured():
    assert "не налаштовано" in await slack.post_message("hi")


async def test_calendar_upcoming_no_ics(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(calendar.settings, "calendar_ics_url", "")

    async def _list(_uid):
        return "немає активних"

    monkeypatch.setattr(calendar, "list_reminders", _list)
    out = await calendar.upcoming(7, user_id=1)
    assert "немає" in out.lower() or "Calendar" in out
