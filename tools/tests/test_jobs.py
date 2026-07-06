"""schedule_job / due_jobs з підробленим Redis (ZSET)."""
import time

import pytest
from app import jobs


class FakeRedis:
    def __init__(self) -> None:
        self.z: dict[str, float] = {}

    async def zadd(self, key, mapping):
        self.z.update(mapping)

    async def zrange(self, key, start, end, withscores=False):
        items = sorted(self.z.items(), key=lambda kv: kv[1])
        sliced = items[start : (None if end == -1 else end + 1)]
        return sliced if withscores else [m for m, _ in sliced]

    async def zrangebyscore(self, key, _min, max_score, start=0, num=20):
        items = sorted(
            [(m, s) for m, s in self.z.items() if s <= float(max_score)],
            key=lambda kv: kv[1],
        )
        chunk = items[start : start + num]
        return [m for m, _ in chunk]

    async def zrem(self, key, member):
        self.z.pop(member, None)


def _inject(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(jobs, "get_redis", lambda: fake)
    return fake


async def test_schedule_and_due_jobs(monkeypatch: pytest.MonkeyPatch):
    fake = _inject(monkeypatch)
    now = int(time.time())
    jid = await jobs.schedule_job(7, now - 10, "stack-status", note="smoke")
    assert len(jid) == 10
    due = await jobs.due_jobs(now=now)
    assert len(due) == 1
    assert due[0]["user_id"] == 7
    assert due[0]["macro"] == "stack-status"
    assert len(fake.z) == 0


async def test_due_jobs_skips_future(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    now = int(time.time())
    await jobs.schedule_job(1, now + 3600, "deploy")
    due = await jobs.due_jobs(now=now)
    assert due == []


async def test_list_jobs_filters_user(monkeypatch: pytest.MonkeyPatch):
    fake = _inject(monkeypatch)
    t = int(time.time()) + 100
    await jobs.schedule_job(42, t, "deploy", note="mine")
    await jobs.schedule_job(99, t, "stack-status")
    out = await jobs.list_jobs(42)
    assert "deploy" in out and "stack-status" not in out
    assert len(fake.z) == 2
