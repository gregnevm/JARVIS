"""AP-1.3/1.4/1.5 — key-management endpoints + /v1 managed-key auth & scopes.

Wired against main's /v1 surface (chat/completions + models)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

ROOT = "sk-root-secret"


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def set(self, key: str, value: str) -> None:
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self.kv.pop(k, None)

    async def sadd(self, key: str, *values: str) -> None:
        self.sets.setdefault(key, set()).update(values)

    async def srem(self, key: str, *values: str) -> None:
        self.sets.get(key, set()).difference_update(values)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def aclose(self) -> None:  # lifespan shutdown
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "enable_openai_api", True)
    monkeypatch.setattr(settings, "openai_api_key", ROOT)
    monkeypatch.setattr(settings, "openai_default_user_id", 42)
    with TestClient(app) as c:
        c.app.state.redis = FakeRedis()
        c.app.state.tools.process = AsyncMock(return_value="ok")
        yield c


def _root() -> dict[str, str]:
    return {"Authorization": f"Bearer {ROOT}"}


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _chat(client: TestClient, headers: dict[str, str]):  # type: ignore[no-untyped-def]
    return client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=headers,
    )


def test_create_requires_root(client: TestClient) -> None:
    assert client.post("/saas/api/keys", json={}, headers=_bearer("nope")).status_code == 403


def test_create_list_revoke_flow(client: TestClient) -> None:
    r = client.post("/saas/api/keys", json={"name": "ci", "scopes": ["chat"]}, headers=_root())
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key.startswith("sk-jarvis-")

    lst = client.get("/saas/api/keys", headers=_root()).json()["data"]
    assert len(lst) == 1 and "key" not in lst[0] and "hash" not in lst[0]
    kid = lst[0]["id"]

    assert _chat(client, _bearer(key)).status_code == 200  # managed key, chat scope
    assert client.delete(f"/saas/api/keys/{kid}", headers=_root()).status_code == 200
    assert _chat(client, _bearer(key)).status_code == 401  # revoked → rejected


def test_revoke_missing_404(client: TestClient) -> None:
    assert client.delete("/saas/api/keys/ghost", headers=_root()).status_code == 404


def test_managed_key_scope_enforced(client: TestClient) -> None:
    # key without 'chat' scope → chat is 403
    key = client.post("/saas/api/keys", json={"scopes": ["models"]}, headers=_root()).json()["key"]
    r = _chat(client, _bearer(key))
    assert r.status_code == 403
    # but /models (any valid key) works
    assert client.get("/v1/models", headers=_bearer(key)).status_code == 200


def test_root_key_bypasses_scopes(client: TestClient) -> None:
    assert _chat(client, _root()).status_code == 200
    assert client.get("/v1/models", headers=_root()).status_code == 200


def test_unknown_key_rejected(client: TestClient) -> None:
    assert _chat(client, _bearer("sk-jarvis-bogus")).status_code == 401
