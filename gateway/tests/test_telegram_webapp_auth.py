"""Telegram WebApp initData для Mini App."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest
from fastapi import HTTPException

from app.config import settings
from app.telegram_webapp_auth import admin_app_url, authorize_admin


def _make_init_data(user_id: int, bot_token: str) -> str:
    user = json.dumps({"id": user_id}, separators=(",", ":"))
    auth_date = str(int(time.time()))
    pairs = {"auth_date": auth_date, "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return f"auth_date={auth_date}&user={quote(user)}&hash={sig}"


def test_admin_app_url_from_public_app(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    monkeypatch.setattr(settings, "public_admin_app_url", "")
    assert admin_app_url() == "https://jarvis.example.com/admin"


def test_authorize_admin(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "1")
    init = _make_init_data(42, "123456:TEST")
    assert authorize_admin(init) == 42


def test_authorize_admin_denied(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST")
    monkeypatch.setattr(settings, "admin_user_ids", "99")
    init = _make_init_data(1, "123456:TEST")
    with pytest.raises(HTTPException) as exc:
        authorize_admin(init)
    assert exc.value.status_code == 403
