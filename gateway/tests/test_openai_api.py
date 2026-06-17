"""OpenAI-compatible API (P11 + AP-2)."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
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


def test_impersonation_uid_ignored(client):
    """P0-4: caller не може зімперсонити uid поза allowed_ids — падає на дефолт 42."""
    captured = {}

    async def _capture(payload):
        captured.update(payload)
        return "ok"

    client.app.state.tools.process = _capture
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "user": "999"},
        headers={"Authorization": "Bearer sk-test", "X-JARVIS-User-Id": "999"},
    )
    assert r.status_code == 200
    assert captured["user_id"] == 42  # 999 проігноровано (не в allowed_ids)


def test_rate_limit_429(client, monkeypatch):
    """P0-5: /v1 застосовує rate-limit (DoS/cost-захист)."""
    class _Block:
        async def allow(self, *a, **k):
            return False

    client.app.state.limiter = _Block()
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 429


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


def test_embeddings_encoding_format_accepted(client, monkeypatch):
    """drop-in compat (#16): OpenAI SDK шле encoding_format — поле приймається й ігнорується."""
    async def _fake_embed(text):
        return [0.5]

    monkeypatch.setattr("app.openai_api._memory_embed", _fake_embed)
    r = client.post(
        "/v1/embeddings",
        json={"input": "hi", "encoding_format": "float"},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 200
    assert r.json()["data"][0]["embedding"] == [0.5]


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
    # #12: 502 піднімається всередині _memory_embed на будь-який збій бекенду.
    async def _boom(text):
        raise HTTPException(status_code=502, detail="embedding backend error: memory down")

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


# --- OpenAI-compatible error envelope (AP-2.6) -------------------------------

def test_error_envelope_on_bad_key(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401
    body = r.json()
    assert "error" in body and body["error"]["type"] == "authentication_error"
    # #12 кладе HTTP-статус у code (int), а не None
    assert body["error"]["message"] and body["error"]["code"] == 401


def test_error_envelope_on_bad_request(client):
    r = client.post(
        "/v1/embeddings",
        json={"input": "  "},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_error_envelope_on_disabled_404(monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_api", False)
    with TestClient(app) as c:
        r = c.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer x"},
        )
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "invalid_request_error"


# --- /v1/jobs async (AP-2.5) -------------------------------------------------

def test_create_job(client):
    client.app.state.tools.create_bg_job = AsyncMock(
        return_value={"id": "job1", "status": "queued", "progress": 0, "created_at": 123}
    )
    r = client.post(
        "/v1/jobs",
        json={"input": "research X", "mode": "agent"},
        headers={"Authorization": "Bearer sk-test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "job1" and body["object"] == "job" and body["status"] == "queued"
    client.app.state.tools.create_bg_job.assert_awaited_once()


def test_create_job_empty_input_400(client):
    r = client.post("/v1/jobs", json={"input": " "}, headers={"Authorization": "Bearer sk-test"})
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_get_job(client):
    client.app.state.tools.get_bg_job = AsyncMock(
        return_value={"id": "job1", "status": "done", "progress": 100, "result": "ok", "created_at": 1}
    )
    r = client.get("/v1/jobs/job1", headers={"Authorization": "Bearer sk-test"})
    assert r.status_code == 200
    assert r.json()["status"] == "done" and r.json()["result"] == "ok"


def test_get_job_not_found_404(client):
    client.app.state.tools.get_bg_job = AsyncMock(return_value=None)
    r = client.get("/v1/jobs/missing", headers={"Authorization": "Bearer sk-test"})
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_jobs_require_auth(client):
    r = client.post("/v1/jobs", json={"input": "x"}, headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
