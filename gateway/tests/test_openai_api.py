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


# --- /v1/embeddings (AP-2.1) -------------------------------------------------

def test_embeddings_single_input(client, monkeypatch):
    async def _fake_embed(text):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("app.openai_api._memory_embed", _fake_embed)
    r = client.post(
        "/v1/embeddings",
        json={"input": "hello", "model": "nomic-embed-text"},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list" and body["model"] == "nomic-embed-text"
    assert len(body["data"]) == 1
    assert body["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert body["data"][0]["index"] == 0


def test_embeddings_batch_input(client, monkeypatch):
    async def _fake_embed(text):
        return [float(len(text))]

    monkeypatch.setattr("app.openai_api._memory_embed", _fake_embed)
    r = client.post(
        "/v1/embeddings",
        json={"input": ["a", "bbb"]},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert [d["index"] for d in data] == [0, 1]
    assert data[0]["embedding"] == [1.0] and data[1]["embedding"] == [3.0]


def test_embeddings_empty_input_400(client):
    r = client.post(
        "/v1/embeddings",
        json={"input": "   "},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 400


def test_embeddings_requires_auth(client):
    r = client.post(
        "/v1/embeddings",
        json={"input": "hi"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_embeddings_backend_error_502(client, monkeypatch):
    import httpx

    async def _boom(text):
        raise httpx.ConnectError("memory down")

    monkeypatch.setattr("app.openai_api._memory_embed", _boom)
    r = client.post(
        "/v1/embeddings",
        json={"input": "hi"},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 502


def test_models_lists_embed_model(client):
    r = client.get("/v1/models", headers={"Authorization": "Bearer sk-test"})
    ids = [m["id"] for m in r.json()["data"]]
    assert "nomic-embed-text" in ids
