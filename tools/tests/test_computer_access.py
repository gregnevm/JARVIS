"""Доступ до Computer Use лише для власника ПК."""
import pytest
from app.computer_access import can_use_computer, computer_denied_message
from app.config import settings


def test_guest_denied_when_owner_list_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "111")
    monkeypatch.setattr(settings, "admin_user_ids", "111,222")
    monkeypatch.setattr(settings, "allowed_user_ids", "111,222,333")
    assert can_use_computer(111)
    assert not can_use_computer(222)
    assert computer_denied_message(222)


def test_fallback_admin_when_owner_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "99")
    assert can_use_computer(42)
    assert not can_use_computer(99)
