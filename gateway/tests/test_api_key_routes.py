"""AP-1.3/1.4/1.5 — key-management endpoints + /v1 managed-key auth & scopes.

Wired against main's /v1 surface (chat/completions + models)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

ROOT = "sk-root-secret"


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.counters: dict[str, int] = {}
        self.h: dict[str, dict[str, int]] = {}

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

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        self.h.setdefault(key, {})[field] = self.h.setdefault(key, {}).get(field, 0) + amount
        return self.h[key][field]

    async def hgetall(self, key: str) -> dict[str, str]:
        return {k: str(v) for k, v in self.h.get(key, {}).items()}

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
    # key with 'models' but not 'chat' → chat is 403, /v1/models works (has the 'models' scope)
    key = client.post("/saas/api/keys", json={"scopes": ["models"]}, headers=_root()).json()["key"]
    assert _chat(client, _bearer(key)).status_code == 403
    assert client.get("/v1/models", headers=_bearer(key)).status_code == 200
    # key with 'chat' but NOT 'models' → /v1/models is now 403 (models scope enforced, AP-1.5)
    key2 = client.post("/saas/api/keys", json={"scopes": ["chat"]}, headers=_root()).json()["key"]
    assert client.get("/v1/models", headers=_bearer(key2)).status_code == 403


def test_all_invalid_scopes_key_is_denied_everywhere(client: TestClient) -> None:
    # a key requested with only invalid scopes (typo) gets NO scopes (least privilege), so it is
    # denied at every scoped endpoint — never silently granted the default scope set.
    made = client.post("/saas/api/keys", json={"scopes": ["admin"]}, headers=_root()).json()
    assert made["scopes"] == []
    key = made["key"]
    assert _chat(client, _bearer(key)).status_code == 403
    assert client.get("/v1/models", headers=_bearer(key)).status_code == 403


def test_root_key_bypasses_scopes(client: TestClient) -> None:
    assert _chat(client, _root()).status_code == 200
    assert client.get("/v1/models", headers=_root()).status_code == 200


def test_unknown_key_rejected(client: TestClient) -> None:
    assert _chat(client, _bearer("sk-jarvis-bogus")).status_code == 401


def test_per_key_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_key_rate_limit_per_min", 2)
    # Пінимо годинник у середині вікна (now=...430 → window starts ...400, reset ...460),
    # щоб усі 3 виклики потрапили в ОДНЕ хвилинне вікно (інакше тест флакає на межі
    # хвилини) і заголовки були детермінованими.
    from app import openai_api

    monkeypatch.setattr(openai_api.time, "time", lambda: 1_700_000_430.0)
    key = client.post("/saas/api/keys", json={"scopes": ["chat"]}, headers=_root()).json()["key"]
    assert _chat(client, _bearer(key)).status_code == 200
    assert _chat(client, _bearer(key)).status_code == 200
    r = _chat(client, _bearer(key))  # 3rd in the same minute → over limit
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "rate_limit_error"
    # стандартні rate-limit заголовки для SDK-backoff (AP-4):
    assert r.headers["x-ratelimit-limit"] == "2"
    assert r.headers["x-ratelimit-remaining"] == "0"
    assert r.headers["retry-after"] == "30"  # 1700000460 - 1700000430
    assert r.headers["x-ratelimit-reset"] == "1700000460"
    # root key is not rate-limited
    assert _chat(client, _root()).status_code == 200


def test_no_rate_limit_when_disabled(client: TestClient) -> None:
    key = client.post("/saas/api/keys", json={"scopes": ["chat"]}, headers=_root()).json()["key"]
    for _ in range(5):
        assert _chat(client, _bearer(key)).status_code == 200
