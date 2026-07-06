"""Cursor task queue helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app import cursor_tasks


@pytest.mark.asyncio
async def test_submit_async(monkeypatch: pytest.MonkeyPatch):
    mock_job = {"id": "j1", "status": "queued"}

    async def _create(*args, **kwargs):
        return mock_job

    monkeypatch.setattr("app.bg_jobs.create_typed_job", _create)
    out = await cursor_tasks.submit(1, "fix tests", async_mode=True)
    assert out["job_id"] == "j1"


@pytest.mark.asyncio
async def test_execute_inbox_when_disabled_host(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cursor_tasks_enabled", True)
    monkeypatch.setattr(settings, "cursor_runtime", "local")
    monkeypatch.setattr(settings, "enable_computer_use", False)
    monkeypatch.setattr(settings, "cursor_api_key", "")
    monkeypatch.setattr(settings, "cursor_repo_url", "")
    out = await cursor_tasks.execute("do thing", user_id=5)
    assert out.get("mode") == "inbox"
    assert out.get("ok") is True


@pytest.mark.asyncio
async def test_execute_local_mock(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cursor_runtime", "local")
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "cursor_host_script", "O:\\JARVIS\\scripts\\cursor_run_task.py")
    monkeypatch.setattr(settings, "cursor_host_workspace", "O:\\JARVIS")

    with patch(
        "app.computer._run_cli_impl",
        AsyncMock(return_value='{"ok":true}\n[exit 0]'),
    ):
        out = await cursor_tasks.execute("add tests")
    assert out.get("ok") is True
    assert out.get("mode") == "local"


def test_format_result_async():
    text = cursor_tasks.format_result({"async": True, "job_id": "abc"})
    assert "abc" in text
