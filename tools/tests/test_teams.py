"""P9 agent teams storage."""
from unittest.mock import AsyncMock

import pytest
from app import teams


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


async def test_create_team(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await teams.create_team(1, "build API", budget_per_role=2)
    assert rec["status"] == "queued"
    assert rec["roles"] == list(teams.DEFAULT_ROLES)


async def test_role_prompts():
    assert "Researcher" in teams.role_system_prompt("researcher")


async def test_create_coding_team_roles(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await teams.create_team(1, "fix bug", roles=list(teams.CODING_ROLES))
    assert rec["roles"] == ["coder", "reviewer", "tester"]


def test_tester_role_prompt():
    assert "Tester" in teams.role_system_prompt("tester")
    assert teams.CODING_ROLES == ("coder", "reviewer", "tester")


async def test_run_team_pipeline_rejects_foreign_team_idor(monkeypatch: pytest.MonkeyPatch):
    """Anti-IDOR: user B не може прогнати/перезаписати team користувача A.

    `POST /teams/run` форвардить caller-supplied team_id; без owner-scope у
    run_team_pipeline user B завантажив би team A, виконав ролі й finish_team
    перезаписав би чужий запис (+ прочитав result). get_team(team_id, user_id)
    фейлить закрито (redis_store owner-gate) → 'team not found', жодної мутації."""
    _inject(monkeypatch)
    agent = AsyncMock()
    agent.run = AsyncMock(return_value={"text": "leaked", "iters": 1})

    rec = await teams.create_team(1, "Owner A task", budget_per_role=2)
    team_id = rec["id"]

    # user 2 намагається прогнати team користувача 1
    out = await teams.run_team_pipeline(agent, 2, team_id)
    assert out == {"error": "team not found"}
    # жодної ролі не виконано — пайплайн не торкнувся agent
    assert agent.run.call_count == 0
    # запис власника A не змінено (лишився 'queued', без result)
    owned = await teams.get_team(team_id, 1)
    assert owned is not None
    assert owned["status"] == "queued"
    assert not owned.get("result")

    # positive: власник A проганяє свою ж team → owner-guard НЕ over-block'ає
    owner_out = await teams.run_team_pipeline(agent, 1, team_id)
    assert owner_out.get("result")
    assert agent.run.call_count == len(owned["roles"])
    done = await teams.get_team(team_id, 1)
    assert done is not None and done["status"] == "done"
