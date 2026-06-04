"""C4 window / UIA toolkit via mocked hostagent."""
from unittest.mock import AsyncMock

import pytest

from app import computer
from app.computer_confirm import is_mutating, tier_for
from app.config import settings


@pytest.fixture(autouse=True)
def computer_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")


async def test_window_list(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        computer,
        "_request",
        AsyncMock(
            return_value={
                "windows": [{"ProcessName": "notepad", "MainWindowTitle": "Untitled"}]
            }
        ),
    )
    out = await computer.window_list(user_id=1)
    assert "notepad" in out


def test_uia_tiers():
    assert tier_for("window_focus") == "T3"
    assert not is_mutating("window_list", {})
    assert is_mutating("uia_invoke", {"control_name": "OK"})
