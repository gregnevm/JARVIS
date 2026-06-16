"""AP-3 developer console data layer: keys + usage via platform (panel) auth."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

PW = "panel-pw"
AUTH = ("admin", PW)


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
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

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        self.h.setdefault(key, {})[field] = self.h.setdefault(key, {}).get(field, 0) + amount
        return self.h[key][field]

    async def hgetall(self, key: str) -> dict[str, str]:
        return {k: str(v) for k, v in self.h.get(key, {}).items()}

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "platform_password", PW)
    with TestClient(app) as c:
        c.app.state.redis = FakeRedis()
        yield c


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/platform/api/developer/keys").status_code == 401


def test_console_key_lifecycle(client: TestClient) -> None:
    # create
    r = client.post(
        "/platform/api/developer/keys", json={"name": "ui", "scopes": ["chat"]}, auth=AUTH
    )
    assert r.status_code == 200, r.text
    key = r.json()
    assert key["key"].startswith("sk-jarvis-") and key["name"] == "ui"
    kid = key["id"]
    # list (no secret leaked)
    data = client.get("/platform/api/developer/keys", auth=AUTH).json()["data"]
    assert any(k["id"] == kid for k in data)
    assert all("key" not in k and "hash" not in k for k in data)
    # usage endpoint responds
    u = client.get("/platform/api/developer/usage?key_id=root", auth=AUTH)
    assert u.status_code == 200 and u.json()["object"] == "usage"
    # revoke + 404 on missing
    assert client.delete(f"/platform/api/developer/keys/{kid}", auth=AUTH).status_code == 200
    assert client.delete("/platform/api/developer/keys/ghost", auth=AUTH).status_code == 404
