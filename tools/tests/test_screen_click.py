"""T4 screen_click."""
from unittest.mock import AsyncMock

import pytest
from app.computer_confirm import is_mutating, tier_for
from app.config import settings


@pytest.fixture(autouse=True)
def computer_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "computer_profile", "full")
    monkeypatch.setattr(settings, "computer_require_confirm", False)


def test_screen_click_tier():
    assert tier_for("screen_click") == "T4"
    assert is_mutating("screen_click", {"x": 1, "y": 2})


async def test_screen_click_dispatch(monkeypatch: pytest.MonkeyPatch):
    from app import computer, toolkit

    monkeypatch.setattr(
        computer,
        "_request",
        AsyncMock(return_value={"status": "ok", "x": "10", "y": "20"}),
    )
    out = await toolkit.dispatch("screen_click", {"x": 10, "y": 20}, user_id=1)
    assert "✅" in out
