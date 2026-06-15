"""Background jobs (P2) — окремо від macro scheduler."""
import json

import pytest

from app import bg_jobs


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, val):
        self.kv[key] = val

    async def get(self, key):
        return self.kv.get(key)

    async def lpush(self, key, val):
        self.lists.setdefault(key, []).insert(0, val)

    async def rpop(self, key):
        lst = self.lists.get(key, [])
        if not lst:
            return None
        return lst.pop()

    async def lrem(self, key, _count, val):
        lst = self.lists.get(key, [])
        while val in lst:
            lst.remove(val)

    async def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        if end == -1:
            end = len(lst) - 1
        return lst[start : end + 1]

    async def ltrim(self, key, start, end):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start : end + 1]


def _inject(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    from app import redis_store

    fake = FakeRedis()
    monkeypatch.setattr(redis_store, "get_redis", lambda: fake)
    monkeypatch.setattr(bg_jobs, "get_redis", lambda: fake)
    return fake


async def test_create_and_get(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await bg_jobs.create_job(42, "hello agent", "agent")
    assert rec["status"] == "queued"
    assert rec["user_id"] == 42
    got = await bg_jobs.get_job(rec["id"])
    assert got is not None
    assert got["payload"]["text"] == "hello agent"


async def test_get_job_ownership_blocks_cross_user(monkeypatch: pytest.MonkeyPatch):
    """IDOR-гейт (SAAS_DEEP_DIVE §4.0): чужий user_id → None, власник → rec,
    без user_id (системний/worker доступ) → rec."""
    _inject(monkeypatch)
    rec = await bg_jobs.create_job(42, "secret task", "agent")
    job_id = rec["id"]
    assert (await bg_jobs.get_job(job_id, 42)) is not None  # власник
    assert (await bg_jobs.get_job(job_id, 999)) is None  # чужий — IDOR заблоковано
    assert (await bg_jobs.get_job(job_id)) is not None  # системний доступ збережено


async def test_dequeue_and_finish(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await bg_jobs.create_job(1, "task", "auto")
    job = await bg_jobs.dequeue_job()
    assert job is not None
    assert job["status"] == "running"
    done = await bg_jobs.finish_job(rec["id"], result="ok", status="done")
    assert done is not None
    assert done["status"] == "done"
    assert done["result"] == "ok"


async def test_cancel_queued(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await bg_jobs.create_job(5, "x", "chat")
    ok = await bg_jobs.cancel_job(rec["id"], 5)
    assert ok is True
    assert (await bg_jobs.get_job(rec["id"]))["status"] == "cancelled"
    assert await bg_jobs.dequeue_job() is None


async def test_list_jobs(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    await bg_jobs.create_job(7, "a", "auto")
    await bg_jobs.create_job(7, "b", "auto")
    items = await bg_jobs.list_jobs(7, limit=10)
    assert len(items) == 2


async def test_create_research_job(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await bg_jobs.create_research_job(3, "quantum computing", 2)
    assert rec["type"] == "deep_research"
    assert rec["payload"]["query"] == "quantum computing"
