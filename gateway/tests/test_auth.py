"""Whitelist-перевірка is_allowed."""
from app.auth import is_allowed
from app.config import settings


def test_none_denied():
    assert is_allowed(None) is False


def test_not_in_list_denied(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "1,2,3")
    assert is_allowed(99) is False


def test_in_list_allowed(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "1,2,3")
    assert is_allowed(2) is True
