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


# --- CA-5.2 coding pipeline (Coder→Reviewer→Tester) --------------------------

async def test_create_coding_team_preserves_roles(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await teams.create_team(1, "fix bug", roles=list(teams.CODING_ROLES))
    assert rec["roles"] == ["coder", "reviewer", "tester"]


def test_tester_role_prompt_mentions_run_tests():
    p = teams.role_system_prompt("tester")
    assert "Tester" in p and "run_tests" in p


class _FakeAgent:
    def __init__(self) -> None:
        self.roles_seen: list[str] = []

    async def run(self, user_id, prompt, *, mode="agent", max_iters_override=None):  # noqa: ANN001
        # однозначний маркер ролі у промпті: "Твій внесок як {role}:"
        for role in ("coder", "reviewer", "tester"):
            if f"внесок як {role}" in prompt:
                self.roles_seen.append(role)
                break
        return {"text": f"output-{len(self.roles_seen)}", "iters": 1}


async def test_coding_pipeline_runs_roles_in_order(monkeypatch: pytest.MonkeyPatch):
    _inject(monkeypatch)
    rec = await teams.create_team(1, "fix bug", roles=list(teams.CODING_ROLES))
    agent = _FakeAgent()
    out = await teams.run_team_pipeline(agent, 1, rec["id"])
    assert agent.roles_seen == ["coder", "reviewer", "tester"]
    assert len(out["steps"]) == 3
    assert [s["role"] for s in out["steps"]] == ["coder", "reviewer", "tester"]
