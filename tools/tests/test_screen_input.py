"""screen_type / screen_hotkey / screen_scroll tools."""
from unittest.mock import AsyncMock

import pytest
from app.config import settings
from app.toolkit import dispatch
from app.toolkit.schemas import agent_tool_schemas


@pytest.fixture()
def computer_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "computer_profile", "full")
    monkeypatch.setattr(settings, "computer_require_confirm", False)


def test_screen_input_schemas_only_in_full_profile(
    computer_full: None, monkeypatch: pytest.MonkeyPatch
):
    names = {s["function"]["name"] for s in agent_tool_schemas(computer=True)}
    assert "screen_type" in names
    assert "screen_hotkey" in names
    assert "screen_scroll" in names
    monkeypatch.setattr(settings, "computer_profile", "safe")
    names_safe = {s["function"]["name"] for s in agent_tool_schemas(computer=True)}
    assert "screen_type" not in names_safe


@pytest.mark.asyncio
async def test_dispatch_screen_hotkey(computer_full: None, monkeypatch: pytest.MonkeyPatch):
    from app import computer

    monkeypatch.setattr(
        computer,
        "_request",
        AsyncMock(return_value={"status": "ok", "keys": "ctrl+s"}),
    )
    out = await dispatch("screen_hotkey", {"keys": ["ctrl", "s"]}, user_id=1)
    assert "Hotkey" in out
