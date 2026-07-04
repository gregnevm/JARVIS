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
from app.telegram_webapp_auth import admin_app_url, authorize_admin, user_id_from_init_data


def _sign(pairs: dict[str, str], bot_token: str) -> str:
    """Validly-signed initData over exactly the given pairs (freshness field is caller-controlled)."""
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    query = "&".join(f"{k}={quote(pairs[k])}" for k in pairs)
    return f"{query}&hash={sig}"


def _make_init_data(user_id: int, bot_token: str) -> str:
    user = json.dumps({"id": user_id}, separators=(",", ":"))
    return _sign({"auth_date": str(int(time.time())), "user": user}, bot_token)


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


@pytest.mark.parametrize(
    "auth_date_field",
    [
        {},                              # auth_date omitted entirely
        {"auth_date": "not-a-date"},     # present but non-numeric
        {"auth_date": " "},              # whitespace (distinct wire input, still non-numeric)
        {"auth_date": str(int(time.time()) - 25 * 3600)},  # numeric but stale (>24h boundary)
    ],
)
def test_init_data_freshness_fails_closed(monkeypatch, auth_date_field):
    """A validly-signed payload whose auth_date can't prove freshness must be rejected (401).

    Pre-fix, a missing/non-numeric auth_date skipped the expiry check entirely — an unbounded
    replay window. The signature covers only present keys, so such a payload still verified."""
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST")
    user = json.dumps({"id": 42}, separators=(",", ":"))
    init = _sign({**auth_date_field, "user": user}, "123456:TEST")
    with pytest.raises(HTTPException) as exc:
        user_id_from_init_data(init)
    assert exc.value.status_code == 401


def test_init_data_fresh_auth_date_accepted(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST")
    user = json.dumps({"id": 42}, separators=(",", ":"))
    init = _sign({"auth_date": str(int(time.time())), "user": user}, "123456:TEST")
    assert user_id_from_init_data(init) == 42
