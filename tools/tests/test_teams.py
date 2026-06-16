"""P9 agent teams storage."""
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
