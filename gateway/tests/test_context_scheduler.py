"""In-app context scheduler: plan_context_run (pure) + run_due (fake redis/post)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.context_scheduler import _daily_key, plan_context_run, run_due

_UTC = timezone.utc


# --- plan_context_run (чиста логіка) ---

def test_plan_before_daily_hour_only_summarize():
    now = datetime(2026, 6, 16, 5, 0, tzinfo=_UTC)
    assert plan_context_run(now, None, daily_hour=6) == ["context_summarize"]


def test_plan_at_daily_hour_first_run_adds_daily_and_retention():
    now = datetime(2026, 6, 16, 6, 30, tzinfo=_UTC)
    jobs = plan_context_run(now, last_daily=None, daily_hour=6)
    assert jobs == ["context_summarize", "context_daily", "context_retention"]


def test_plan_skips_daily_if_already_ran_today():
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_UTC)
    jobs = plan_context_run(now, last_daily="2026-06-16", daily_hour=6)
    assert jobs == ["context_summarize"]


# --- run_due (fake redis + post) ---

class FakeRedis:
    def __init__(self, store: dict | None = None) -> None:
        self.store = store or {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value


class FakePost:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail or set()

    async def __call__(self, path, params):
        self.calls.append((path, params))
        name = path.rsplit("/", 1)[-1]
        if name in self.fail:
            raise RuntimeError("tools down")
        return {"job": name}


async def test_run_due_first_daily_run_executes_all_and_marks_redis():
    redis = FakeRedis()
    post = FakePost()
    now = datetime(2026, 6, 16, 7, 0, tzinfo=_UTC)
    ran = await run_due(redis, post, [42], now=now, daily_hour=6)
    assert ran == {"summarize": 1, "daily": 1, "retention": 1}
    paths = [p for p, _ in post.calls]
    assert paths == ["/context/jobs/context_summarize", "/context/jobs/context_daily",
                     "/context/jobs/context_retention"]
    assert redis.store[_daily_key(42)] == "2026-06-16"  # guard виставлено


async def test_run_due_second_run_same_day_only_summarize():
    redis = FakeRedis({_daily_key(42): "2026-06-16"})
    post = FakePost()
    now = datetime(2026, 6, 16, 9, 0, tzinfo=_UTC)
    ran = await run_due(redis, post, [42], now=now, daily_hour=6)
    assert ran["daily"] == 0 and ran["summarize"] == 1


async def test_run_due_daily_failure_does_not_mark_guard():
    redis = FakeRedis()
    post = FakePost(fail={"context_daily"})
    now = datetime(2026, 6, 16, 7, 0, tzinfo=_UTC)
    ran = await run_due(redis, post, [42], now=now, daily_hour=6)
    assert ran["daily"] == 0  # daily впала
    # guard НЕ виставлено → завтрашній (чи наступний) тік спробує знову
    assert _daily_key(42) not in redis.store


async def test_run_due_multiple_users():
    redis = FakeRedis()
    post = FakePost()
    now = datetime(2026, 6, 16, 7, 0, tzinfo=_UTC)
    ran = await run_due(redis, post, [1, 2], now=now, daily_hour=6)
    assert ran["summarize"] == 2 and ran["daily"] == 2
