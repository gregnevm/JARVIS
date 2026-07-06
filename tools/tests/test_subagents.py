"""P8 subagents storage."""
import pytest
from app import subagents


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


async def test_create_spawn(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await subagents.create_spawn(5, "analyze logs", budget_iters=2)
    assert rec["status"] == "queued"
    assert rec["budget_iters"] == 2


async def test_finish_run(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await subagents.create_spawn(1, "task")
    await subagents.mark_running(rec["id"])
    done = await subagents.finish_run(rec["id"], result="ok", iters_used=2)
    assert done is not None
    assert done["status"] == "done"
