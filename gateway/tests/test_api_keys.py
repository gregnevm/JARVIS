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


async def test_verify_never_writes_record_key() -> None:
    # Інваріант: read-path (verify) НЕ пише запис ключа — інакше read-modify-write
    # гоняється з revoke() і воскрешає відкликаний ключ (auth-bypass).
    fr = FakeRedis()
    store = ApiKeyStore(fr)
    created = await store.create()
    writes: list[str] = []
    orig_set = fr.set

    async def spy_set(key: str, value: str) -> None:
        writes.append(key)
        await orig_set(key, value)

    fr.set = spy_set  # type: ignore[method-assign]
    assert await store.verify(created["key"]) is not None
    # whitelist: ЄДИНИЙ запис — side-ключ last_used (жодного rec:/pfx:/index)
    assert writes == [f"jarvis:apikey:used:{created['id']}"]


async def test_failed_verify_writes_nothing() -> None:
    # Відхилений verify (revoked / tampered) не пише НІЧОГО — інакше майбутній
    # реордер side-запису вище guard-ів тихо зіпсує аудит-семантику last_used.
    fr = FakeRedis()
    store = ApiKeyStore(fr)
    created = await store.create()
    await store.revoke(created["id"])
    writes: list[str] = []
    orig_set = fr.set

    async def spy_set(key: str, value: str) -> None:
        writes.append(key)
        await orig_set(key, value)

    fr.set = spy_set  # type: ignore[method-assign]
    assert await store.verify(created["key"]) is None  # revoked
    tampered = created["key"][: len("sk-jarvis-") + 8] + "XXXXXXXXXXXX"
    assert await store.verify(tampered) is None  # bad hash (інший, не-revoked шлях)
    assert writes == []


async def test_revoke_during_verify_stays_revoked(store: ApiKeyStore) -> None:
    # Регресія на гонку: revoke() завершується МІЖ _load() усередині verify()
    # і хвостом verify(). Старий код писав пре-revoke запис назад → ключ
    # автентифікувався вічно. Тепер revoked має лишитися true, а повторний
    # verify — відхилити ключ.
    created = await store.create()
    real_load = store._load
    raced = {"done": False}

    async def racing_load(key_id: str) -> dict[str, object] | None:
        rec = await real_load(key_id)
        if not raced["done"]:
            raced["done"] = True  # до revoke(): він сам викликає _load → без рекурсії
            await store.revoke(created["id"])
        return rec  # verify отримує СТАРИЙ (пре-revoke) запис — як у реальній гонці

    store._load = racing_load  # type: ignore[method-assign]
    await store.verify(created["key"])  # in-flight запит; головне — стан ПІСЛЯ нього
    store._load = real_load  # type: ignore[method-assign]

    pub = await store.get(created["id"])
    assert pub is not None and pub["revoked"] is True  # відкликання НЕ перезаписано
    assert await store.verify(created["key"]) is None  # наступний запит відхилено


async def test_last_used_surfaces_via_get_and_list(store: ApiKeyStore) -> None:
    created = await store.create(name="used")
    assert (await store.get(created["id"]))["last_used_at"] is None  # type: ignore[index]
    verified = await store.verify(created["key"])
    assert verified is not None and isinstance(verified["last_used_at"], int)
    pub = await store.get(created["id"])
    assert pub is not None and pub["last_used_at"] == verified["last_used_at"]
    listed = {i["id"]: i for i in await store.list()}
    assert listed[created["id"]]["last_used_at"] == verified["last_used_at"]


async def test_last_used_legacy_record_fallback() -> None:
    # Записи, створені ДО side-ключа, несуть last_used_at у самому rec —
    # без side-ключа get()/list() мають віддавати legacy-значення.
    import json

    fr = FakeRedis()
    store = ApiKeyStore(fr)
    created = await store.create()
    rec_key = f"jarvis:apikey:rec:{created['id']}"
    legacy = json.loads(fr.kv[rec_key])
    legacy["last_used_at"] = 1750000000
    fr.kv[rec_key] = json.dumps(legacy)
    pub = await store.get(created["id"])
    assert pub is not None and pub["last_used_at"] == 1750000000
    # side-ключ має ПРІОРИТЕТ над legacy-полем (стан старого запису після
    # першого post-deploy verify)
    verified = await store.verify(created["key"])
    assert verified is not None
    pub2 = await store.get(created["id"])
    assert pub2 is not None and pub2["last_used_at"] == verified["last_used_at"] != 1750000000
    # зіпсований side-ключ → фолбек на legacy-значення, list() не падає
    fr.kv[f"jarvis:apikey:used:{created['id']}"] = "garbage"
    pub3 = await store.get(created["id"])
    assert pub3 is not None and pub3["last_used_at"] == 1750000000
    assert any(i["id"] == created["id"] for i in await store.list())


async def test_scope_normalization_drops_invalid_least_privilege(store: ApiKeyStore) -> None:
    # partial-invalid: keep the valid scopes, drop the unknown ones
    out = await store.create(scopes=["bogus", "chat"])
    assert out["scopes"] == ["chat"]  # bogus відкинуто
    # ALL-invalid (e.g. a typo like ["admin"]): NO scopes granted — least privilege. Previously this
    # silently fell back to ALL default scopes, broadening the caller's requested privilege.
    out2 = await store.create(scopes=["bogus"])
    assert out2["scopes"] == []
    # unspecified (None / empty) still means the default scope set
    assert set((await store.create(scopes=None))["scopes"]) == {"chat", "models", "embeddings", "jobs"}
    assert set((await store.create(scopes=[]))["scopes"]) == {"chat", "models", "embeddings", "jobs"}
