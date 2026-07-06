"""Тести веб-панелі /admin."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


def _auth_header(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _make_init_data(user_id: int, bot_token: str) -> str:
    user = json.dumps({"id": user_id}, separators=(",", ":"))
    auth_date = str(int(time.time()))
    pairs = {"auth_date": auth_date, "user": user}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return f"auth_date={auth_date}&user={quote(user)}&hash={sig}"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_panel_password", "secret")
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST")
    monkeypatch.setattr(settings, "allowed_user_ids", "1")
    monkeypatch.setattr(settings, "admin_user_ids", "1")
    with TestClient(app) as c:
        yield c


def test_admin_html_open_without_auth(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "JARVIS Admin" in r.text


def test_api_disabled_without_auth_or_password(monkeypatch):
    monkeypatch.setattr(settings, "admin_panel_password", "")
    monkeypatch.setattr(settings, "access_store_path", "/tmp/users.json")
    with TestClient(app) as c:
        r = c.get("/admin/api/overview")
    assert r.status_code == 503


def test_panel_requires_basic_auth(client):
    r = client.get("/admin/api/overview")
    assert r.status_code == 401


def test_panel_bad_password(client):
    r = client.get("/admin/api/overview", headers=_auth_header("admin", "wrong"))
    assert r.status_code == 401


def test_overview_api_basic(client):
    r = client.get("/admin/api/overview", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert "access" in data
    assert "settings" in data
    assert data.get("auth_via") == "basic"


def test_overview_api_telegram_admin(client):
    init = _make_init_data(1, "123456:TEST")
    r = client.get(
        "/admin/api/overview",
        headers={"X-Telegram-Init-Data": init},
    )
    assert r.status_code == 200
    assert r.json().get("auth_via") == "telegram"


def test_overview_api_telegram_non_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "99")
    init = _make_init_data(1, "123456:TEST")
    r = client.get("/admin/api/overview", headers={"X-Telegram-Init-Data": init})
    assert r.status_code == 403


def test_health_api(client):
    r = client.get("/admin/api/health", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    assert "stack" in r.json()
