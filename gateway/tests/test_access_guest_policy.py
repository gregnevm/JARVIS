"""Політика доступу: режим лише адмін; Computer Use — лише власник ПК."""
import pytest
from app.access_store import AccessStore
from app.auth import (
    agent_mode_denied_message,
    bind_access_store,
    can_change_agent_mode,
    can_use_computer,
    can_use_computer_mode,
    is_allowed,
)


def test_mode_change_admin_only(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.allowed_user_ids", "1,2")
    monkeypatch.setattr("app.config.settings.admin_user_ids", "1")
    assert can_change_agent_mode(1)
    assert not can_change_agent_mode(2)
    assert agent_mode_denied_message(2)


@pytest.mark.asyncio
async def test_computer_denied_for_bot_friend(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.allowed_user_ids", "1")
    monkeypatch.setattr("app.config.settings.admin_user_ids", "1")
    monkeypatch.setattr("app.config.settings.computer_owner_user_ids", "1")
    store = AccessStore(tmp_path / "users.json")
    bind_access_store(store)
    await store.approve(2, by_admin=1)
    assert is_allowed(2)
    assert not can_use_computer(2)
    assert not can_use_computer_mode(2)
    bind_access_store(None)
