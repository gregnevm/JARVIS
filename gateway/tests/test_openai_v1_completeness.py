"""AP-2.1 embeddings + AP-2.6 OpenAI error envelope on /v1."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "enable_openai_api", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_default_user_id", 42)
    with TestClient(app) as c:
        yield c


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer sk-test"}


def test_embeddings_single(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.openai_api._memory_embed", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    r = client.post("/v1/embeddings", json={"input": "hello"}, headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "list" and body["model"] == "nomic-embed-text"
    assert body["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert body["data"][0]["index"] == 0


def test_embeddings_batch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.openai_api._memory_embed", AsyncMock(return_value=[1.0]))
    r = client.post("/v1/embeddings", json={"input": ["a", "b"]}, headers=_auth())
    assert r.status_code == 200
    data = r.json()["data"]
    assert [d["index"] for d in data] == [0, 1]


def test_embeddings_empty_input_400(client: TestClient) -> None:
    r = client.post("/v1/embeddings", json={"input": "   "}, headers=_auth())
    assert r.status_code == 400
    # AP-2.6: error envelope shape
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_embeddings_backend_error_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.openai_api._memory_embed", AsyncMock(side_effect=__import__("fastapi").HTTPException(502, "boom"))
    )
    r = client.post("/v1/embeddings", json={"input": "x"}, headers=_auth())
    assert r.status_code == 502
    assert r.json()["error"]["type"] == "api_error"


def test_error_envelope_on_bad_key(client: TestClient) -> None:
    r = client.post("/v1/embeddings", json={"input": "x"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["type"] == "authentication_error" and err["code"] == 401


def test_models_lists_embeddings(client: TestClient) -> None:
    r = client.get("/v1/models", headers=_auth())
    ids = {m["id"] for m in r.json()["data"]}
    assert "nomic-embed-text" in ids
