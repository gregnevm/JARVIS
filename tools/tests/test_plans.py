"""P3 plans storage."""
import pytest

from app import plans


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, val, ex=None):
        self.kv[key] = val

    async def get(self, key):
        return self.kv.get(key)

    async def lpush(self, key, val):
        self.lists.setdefault(key, []).insert(0, val)

    async def ltrim(self, key, start, end):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start : end + 1]

    async def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        if end == -1:
            end = len(lst) - 1
        return lst[start : end + 1]


def _inject(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    from app import redis_store

    fake = FakeRedis()
    monkeypatch.setattr(redis_store, "get_redis", lambda: fake)
    return fake


async def test_create_and_approve(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await plans.create_plan(
        1,
        summary="Test plan",
        steps=[{"title": "Step 1", "detail": "Do thing"}],
        risks=["risk"],
    )
    assert rec["status"] == "pending"
    approved = await plans.approve_plan(rec["id"], 1)
    assert approved is not None
    assert approved["status"] == "approved"


async def test_deny_and_advance(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await plans.create_plan(2, summary="x", steps=["a", "b"])
    assert len(rec["steps"]) == 2
    await plans.set_executing(rec["id"])
    updated = await plans.advance_step(rec["id"], 0, status="done")
    assert updated is not None
    assert updated["steps"][0]["status"] == "done"
    await plans.deny_plan(rec["id"], 2)
    got = await plans.get_plan(rec["id"])
    assert got is not None
