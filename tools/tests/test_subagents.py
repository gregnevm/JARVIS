"""P8 subagents storage."""
import asyncio
from unittest.mock import AsyncMock

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


def test_subagents_run_rejects_foreign_run_idor(monkeypatch: pytest.MonkeyPatch):
    """Anti-IDOR route guard: user B не може прогнати/перезаписати run користувача A.

    `POST /subagents/run` форвардить caller-supplied run_id у mark_running/finish_run,
    які переписують запис (status/result/iters). Без owner-check user B перезаписав би
    чужий run. Гард робить get_run(run_id, user_id) → 404 при mismatch, до будь-якої
    мутації й до запуску агента. Sync-тест: TestClient крутить власний loop, seeding —
    через asyncio.run (FakeRedis = чистий dict, без loop-affinity).

    app.routes тягне Unix-only 'resource' (toolkit.sandbox) → importorskip робить
    цей тест CI-only (Linux); локальний Windows-гейт пропускає, як і всі route-тести репо."""
    subagents_routes = pytest.importorskip(
        "app.routes.subagents",
        reason="app.routes imports Unix-only 'resource' (toolkit.sandbox); route test runs on CI",
    )
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    _inject(monkeypatch)
    rec = asyncio.run(subagents.create_spawn(1, "owner A task", budget_iters=2))
    run_id = rec["id"]

    app = FastAPI()
    router = APIRouter()
    subagents_routes.register(router)
    app.include_router(router)
    agent = AsyncMock()
    agent.run = AsyncMock(return_value={"text": "leaked", "iters": 1})
    app.state.agent = agent
    client = TestClient(app)

    # user 2 намагається прогнати run користувача 1
    r = client.post("/subagents/run", json={"run_id": run_id, "user_id": 2, "task": "x"})
    assert r.status_code == 404
    # пайплайн не торкнувся агента (fail closed до мутації)
    assert agent.run.call_count == 0
    # запис власника A не змінено (лишився 'queued', без result)
    owned = asyncio.run(subagents.get_run(run_id, 1))
    assert owned is not None
    assert owned["status"] == "queued"
    assert not owned.get("result")

    # positive: власник (user 1) проганяє свій run → owner-guard НЕ over-block'ає
    r2 = client.post("/subagents/run", json={"run_id": run_id, "user_id": 1, "task": "x"})
    assert r2.status_code == 200
    assert agent.run.call_count == 1
    done = asyncio.run(subagents.get_run(run_id, 1))
    assert done is not None and done["status"] == "done"
