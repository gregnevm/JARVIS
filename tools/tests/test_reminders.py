"""add_reminder / list_reminders з підробленим Redis (ZSET), без мережі."""
import json
import time

from app import reminders, toolkit


class FakeRedis:
    def __init__(self) -> None:
        self.z: dict[str, float] = {}

    async def zadd(self, key, mapping):
        self.z.update(mapping)

    async def zrange(self, key, start, end, withscores=False):
        items = sorted(self.z.items(), key=lambda kv: kv[1])
        sliced = items[start : (None if end == -1 else end + 1)]
        return sliced if withscores else [m for m, _ in sliced]

    async def aclose(self):
        pass


def _inject(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(reminders, "get_redis", lambda: fake)
    return fake


async def test_add_reminder_stores_with_future_score(monkeypatch):
    fake = _inject(monkeypatch)
    out = await reminders.add_reminder(42, 30, "купити хліб")
    assert "Нагадаю" in out
    assert len(fake.z) == 1
    member, score = next(iter(fake.z.items()))
    rec = json.loads(member)
    assert rec["user_id"] == 42 and rec["text"] == "купити хліб"
    assert score >= time.time() + 30 * 60 - 5  # ~через 30 хв


async def test_add_reminder_rejects_empty_and_past(monkeypatch):
    _inject(monkeypatch)
    assert "Порожнє" in await reminders.add_reminder(1, 10, "   ")
    assert "майбутньому" in await reminders.add_reminder(1, 0, "щось")
    assert "майбутньому" in await reminders.add_reminder(1, -5, "щось")


async def test_list_reminders_filters_by_user(monkeypatch):
    _inject(monkeypatch)
    await reminders.add_reminder(42, 10, "моє")
    await reminders.add_reminder(99, 10, "чуже")
    out = await reminders.list_reminders(42)
    assert "моє" in out and "чуже" not in out


async def test_list_reminders_empty(monkeypatch):
    _inject(monkeypatch)
    assert "немає" in await reminders.list_reminders(42)


async def test_dispatch_routes_reminder_tools(monkeypatch):
    _inject(monkeypatch)
    res = await toolkit.dispatch("set_reminder", {"text": "тест", "delay_minutes": 15}, user_id=7)
    assert "Нагадаю" in res
    lst = await toolkit.dispatch("list_reminders", {}, user_id=7)
    assert "тест" in lst
