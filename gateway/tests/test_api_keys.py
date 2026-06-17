"""API-key store (AP-1.2/1.3): create / list / revoke / verify, hash-only storage."""
from __future__ import annotations

import pytest

from app.saas.api_keys import ApiKeyStore, generate_key


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


@pytest.fixture()
def store() -> ApiKeyStore:
    return ApiKeyStore(FakeRedis())


def test_generate_key_shape() -> None:
    full, prefix, h = generate_key()
    assert full.startswith("sk-jarvis-")
    assert prefix == full[: len("sk-jarvis-") + 8]
    assert len(h) == 64 and h != full  # sha256 hex, not the raw key


async def test_create_returns_key_once_and_stores_hash_only(store: ApiKeyStore) -> None:
    out = await store.create(name="ci", scopes=["chat"])
    assert out["key"].startswith("sk-jarvis-") and out["name"] == "ci"
    assert out["scopes"] == ["chat"] and out["revoked"] is False
    # збережений запис не містить сирого ключа
    rec = await store._load(out["id"])
    assert rec is not None and "hash" in rec
    assert "key" not in rec and rec["hash"] != out["key"]
    # публічний get не віддає hash
    pub = await store.get(out["id"])
    assert pub is not None and "hash" not in pub and "key" not in pub


async def test_verify_roundtrip(store: ApiKeyStore) -> None:
    created = await store.create()
    rec = await store.verify(created["key"])
    assert rec is not None and rec["id"] == created["id"]
    assert rec["last_used_at"] is not None


async def test_verify_rejects_unknown_and_garbage(store: ApiKeyStore) -> None:
    assert await store.verify("sk-jarvis-totallybogus") is None
    assert await store.verify("not-a-key") is None
    assert await store.verify("") is None


async def test_verify_rejects_revoked(store: ApiKeyStore) -> None:
    created = await store.create()
    assert await store.revoke(created["id"]) is True
    assert await store.verify(created["key"]) is None
    # публічний запис позначений revoked
    pub = await store.get(created["id"])
    assert pub is not None and pub["revoked"] is True


async def test_verify_rejects_tampered_same_prefix(store: ApiKeyStore) -> None:
    created = await store.create()
    # той самий prefix, інший хвіст → хеш не збігається
    tampered = created["key"][: len("sk-jarvis-") + 8] + "XXXXXXXXXXXX"
    assert await store.verify(tampered) is None


async def test_list_sorted_no_secrets(store: ApiKeyStore) -> None:
    a = await store.create(name="a")
    b = await store.create(name="b")
    items = await store.list()
    ids = {i["id"] for i in items}
    assert {a["id"], b["id"]} <= ids
    assert all("hash" not in i and "key" not in i for i in items)


async def test_revoke_missing_returns_false(store: ApiKeyStore) -> None:
    assert await store.revoke("nope") is False


async def test_invalid_scopes_fall_back_to_default(store: ApiKeyStore) -> None:
    out = await store.create(scopes=["bogus", "chat"])
    assert out["scopes"] == ["chat"]  # bogus відкинуто
    out2 = await store.create(scopes=["bogus"])
    assert set(out2["scopes"]) == {"chat", "models", "embeddings", "jobs"}  # невалідні → дефолт
