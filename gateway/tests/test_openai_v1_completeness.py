"""AP-2.1 embeddings + AP-2.6 OpenAI error envelope on /v1."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class FakeRedis:
    def __init__(self) -> None:
        self.h: dict[str, dict[str, int]] = {}

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        bucket = self.h.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount
        return bucket[field]

    async def hgetall(self, key: str) -> dict[str, str]:
        return {k: str(v) for k, v in self.h.get(key, {}).items()}

    # /v1 auth uses key store (verify) only for non-root tokens; root path skips it.
    async def get(self, key: str) -> str | None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "enable_openai_api", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_default_user_id", 42)
    with TestClient(app) as c:
        c.app.state.redis = FakeRedis()
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


def test_create_job(client: TestClient) -> None:
    client.app.state.tools.create_bg_job = AsyncMock(
        return_value={"id": "job_1", "status": "queued", "created_at": 100, "kind": "research"}
    )
    r = client.post("/v1/jobs", json={"input": "research X", "mode": "research"}, headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "job_1" and body["object"] == "job" and body["status"] == "queued"


def test_create_job_empty_400(client: TestClient) -> None:
    r = client.post("/v1/jobs", json={"input": "  "}, headers=_auth())
    assert r.status_code == 400


def test_create_job_backend_error_502(client: TestClient) -> None:
    client.app.state.tools.create_bg_job = AsyncMock(return_value={"error": "tools unavailable"})
    r = client.post("/v1/jobs", json={"input": "x"}, headers=_auth())
    assert r.status_code == 502


def test_get_job_and_404(client: TestClient) -> None:
    client.app.state.tools.get_bg_job = AsyncMock(
        return_value={"id": "job_1", "status": "done", "result": "ok", "created_at": 1}
    )
    r = client.get("/v1/jobs/job_1", headers=_auth())
    assert r.status_code == 200 and r.json()["result"] == "ok"
    client.app.state.tools.get_bg_job = AsyncMock(return_value=None)
    assert client.get("/v1/jobs/ghost", headers=_auth()).status_code == 404


def test_responses_string_input(client: TestClient) -> None:
    client.app.state.tools.process = AsyncMock(return_value="agent answer")
    r = client.post("/v1/responses", json={"input": "do a thing"}, headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "response" and body["status"] == "completed"
    assert body["output_text"] == "agent answer"
    assert body["output"][0]["content"][0]["text"] == "agent answer"


def test_responses_list_input(client: TestClient) -> None:
    process = AsyncMock(return_value="ok")
    client.app.state.tools.process = process
    r = client.post(
        "/v1/responses",
        json={"input": [{"role": "user", "content": "hello agent"}]},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert process.await_args.args[0]["text"] == "hello agent"
    assert process.await_args.args[0]["mode"] == "agent"


def test_responses_empty_400(client: TestClient) -> None:
    r = client.post("/v1/responses", json={"input": "   "}, headers=_auth())
    assert r.status_code == 400


def test_usage_records_and_reports(client: TestClient) -> None:
    # кілька викликів /v1 → лічильники ростуть
    client.get("/v1/models", headers=_auth())
    client.get("/v1/models", headers=_auth())
    r = client.get("/v1/usage", headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "usage" and body["key_id"] == "root"
    # 2 models + цей usage-виклик = 3 запити; /v1/models у by_endpoint
    assert body["total_requests"] >= 3
    assert body["by_endpoint"].get("/v1/models") == 2
