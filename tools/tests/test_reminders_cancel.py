import json
import time

import pytest

from app.reminders import REMINDERS_KEY, add_reminder, cancel_reminder, list_reminders


@pytest.fixture()
def fake_redis(monkeypatch):
    store: dict[str, dict[str, float]] = {}

    class R:
        async def zadd(self, key, mapping):
            store.setdefault(key, {}).update(mapping)

        async def zrange(self, key, start, end, withscores=False):
            items = sorted(store.get(key, {}).items(), key=lambda x: x[1])
            if withscores:
                return items
            return [m for m, _ in items]

        async def zrem(self, key, member):
            store.get(key, {}).pop(member, None)

    r = R()
    monkeypatch.setattr("app.reminders.get_redis", lambda: r)
    return store


async def test_cancel_reminder_by_id(fake_redis):
    await add_reminder(42, 60, "test one")
    body = await list_reminders(42)
    assert "test one" in body
    rid = body.split("<code>")[1].split("</code>")[0]
    out = await cancel_reminder(42, rid)
    assert "Скасовано" in out
    body2 = await list_reminders(42)
    assert "немає" in body2.lower()
