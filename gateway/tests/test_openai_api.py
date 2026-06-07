"""OpenAI-compatible API (P11)."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_api", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_default_user_id", 42)
    monkeypatch.setattr(settings, "allowed_user_ids", "42")

    with TestClient(app) as c:
        c.app.state.tools.process = AsyncMock(return_value="Hello from JARVIS")
        yield c


def test_disabled_returns_404(monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_api", False)
    with TestClient(app) as c:
        r = c.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer sk-test"},
        )
        assert r.status_code == 404


def test_chat_completions(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "Hello from JARVIS"


def test_bad_key(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401
