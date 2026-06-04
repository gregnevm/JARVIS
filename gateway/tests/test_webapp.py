"""Тести Mini App /app."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "webapp_dev_open", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    with TestClient(app) as c:
        yield c


def test_app_html(client):
    r = client.get("/app")
    assert r.status_code == 200
    assert "JARVIS" in r.text
    assert 'fetch("/app/data"' in r.text or 'const API = "/app"' in r.text


def test_app_data_dev_open(client):
    r = client.get("/app/data")
    assert r.status_code == 200
    data = r.json()
    assert "core" in data
    assert "twin" in data
    assert "ts" in data
