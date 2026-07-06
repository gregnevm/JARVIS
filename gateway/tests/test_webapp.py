"""Тести Mini App /app."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "webapp_dev_open", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    async def _fake_flags(_redis):
        return {
            "streaming": True,
            "voice_reply": False,
            "streaming_default": True,
            "voice_default": False,
        }

    monkeypatch.setattr("app.webapp.get_flags", _fake_flags)
    with TestClient(app) as c:
        yield c


def test_app_html(client):
    r = client.get("/app")
    assert r.status_code == 200
    assert "JARVIS" in r.text
    assert 'const API = "/app"' in r.text
    assert "panelPs" in r.text
    assert "/ps/ask" in r.text


def test_app_data_dev_open(client):
    r = client.get("/app/data")
    assert r.status_code == 200
    data = r.json()
    assert "core" in data
    assert "twin" in data
    assert "ts" in data
    assert "flags" in data


def test_app_ping(client):
    r = client.get("/app/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_app_no_cache(client):
    r = client.get("/app")
    assert r.headers.get("cache-control", "").startswith("no-store")


def test_twin_versions_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "0")
    app.state.svc.twin_lora_versions = AsyncMock(
        return_value={"versions": [{"version": "v0.1", "status": "candidate"}]}
    )
    r = client.get("/app/twin/versions")
    assert r.status_code == 200
    assert r.json()["versions"][0]["version"] == "v0.1"


def test_twin_versions_forbidden(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "999")
    r = client.get("/app/twin/versions")
    assert r.status_code == 403


def test_dev_open_anon_cannot_mutate(client):
    """P0-2: dev-open uid 0 (анонім) не виконує мутуючі privileged-дії.

    GET-перегляд дозволений (test_app_data_dev_open), але mode/trust/macro —
    403 'identified user required'. Так uid-0 sentinel не оминає guard через falsy-0.
    """
    assert client.post("/app/mode", json={"mode": "agent"}).status_code == 403
    assert client.post("/app/trust").status_code == 403
    assert client.post("/app/macro/anything").status_code == 403
