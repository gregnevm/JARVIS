"""Тести веб-панелі /admin."""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _auth_header(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_panel_password", "secret")
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "allowed_user_ids", "1")
    monkeypatch.setattr(settings, "admin_user_ids", "1")
    with TestClient(app) as c:
        yield c


def test_panel_disabled_without_password(monkeypatch):
    monkeypatch.setattr(settings, "admin_panel_password", "")
    with TestClient(app) as c:
        r = c.get("/admin")
    assert r.status_code == 503


def test_panel_requires_auth(client):
    r = client.get("/admin")
    assert r.status_code == 401


def test_panel_bad_password(client):
    r = client.get("/admin", headers=_auth_header("admin", "wrong"))
    assert r.status_code == 401


def test_panel_html_ok(client):
    r = client.get("/admin", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    assert "JARVIS Admin" in r.text


def test_overview_api(client):
    r = client.get("/admin/api/overview", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert "access" in data
    assert "core" in data
    assert "settings" in data
    assert "services" in data
    assert "stack" in data


def test_health_api(client):
    r = client.get("/admin/api/health", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    assert "stack" in r.json()
