"""Cursor Telegram flow."""
import pytest

from app.bot.cursor_flow import can_use_cursor, format_status, try_extract_cursor_task


def test_can_use_cursor_admin(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_user_ids", "42")
    assert can_use_cursor(42) is True
    assert can_use_cursor(99) is False


def test_extract_cursor_prefix():
    assert try_extract_cursor_task("cursor: fix bug") == "fix bug"
    assert try_extract_cursor_task("cursor add tests") == "add tests"
    assert try_extract_cursor_task("курсор: refactor") == "refactor"


def test_extract_computer_mode():
    assert try_extract_cursor_task("cursor задача: add tests", computer_mode=True) == "add tests"
    assert try_extract_cursor_task("hello", computer_mode=False) is None


@pytest.mark.asyncio
async def test_format_status_empty():
    class FakeTools:
        async def list_bg_jobs(self, user_id, limit=20):
            return [{"id": "j1", "type": "agent_turn", "status": "done"}]

    text = await format_status(FakeTools(), 1)
    assert "немає" in text
