"""Reminders ICS export."""
import json
import time

import pytest

from app import reminders


class FakeRedis:
    def __init__(self) -> None:
        self.z: dict[str, float] = {}

    async def zrange(self, key, start, end, withscores=False):
        assert key == reminders.REMINDERS_KEY
        items = sorted(self.z.items(), key=lambda x: x[1])
        if withscores:
            return items
        return [m for m, _ in items]

    async def zadd(self, key, mapping):
        self.z.update(mapping)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    fr = FakeRedis()
    monkeypatch.setattr(reminders, "_redis", fr)
    return fr


async def test_export_ics(fake_redis: FakeRedis):
    due = int(time.time()) + 3600
    member = json.dumps({"id": "ab12", "user_id": 7, "text": "Test meet"})
    fake_redis.z[member] = float(due)
    body = await reminders.export_ics(7)
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "Test meet" in body
    assert await reminders.export_ics(99) == ""
