"""Phase 7.1 Orchestrator + Critic."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.orchestrator import parse_critic_verdict, run_orchestrator_pipeline


def test_parse_critic_json_approved():
    raw = '{"approved": true, "issues": [], "feedback": "ok"}'
    v = parse_critic_verdict(raw)
    assert v["approved"] is True
    assert v["issues"] == []


def test_parse_critic_json_rejected():
    raw = '{"approved": false, "issues": ["fact error"], "feedback": "fix"}'
    v = parse_critic_verdict(raw)
    assert v["approved"] is False
    assert "fact error" in v["issues"][0]


def test_parse_critic_text_fallback():
    assert parse_critic_verdict("APPROVED — looks good")["approved"] is True
    assert parse_critic_verdict("NOT APPROVED: missing data")["approved"] is False


@pytest.mark.asyncio
async def test_orchestrator_pipeline_approved_first_round(monkeypatch: pytest.MonkeyPatch):
    from app import orchestrator as orch_mod

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
            return lst[start : end + 1]

    from app import redis_store

    fake = FakeRedis()
    monkeypatch.setattr(redis_store, "get_redis", lambda: fake)

    chat = AsyncMock()
    chat.chat = AsyncMock(
        side_effect=[
            {"content": "Plan: step 1"},
            {"content": '{"approved": true, "issues": [], "feedback": "ok"}'},
        ]
    )
    agent = AsyncMock()
    agent.run = AsyncMock(return_value={"text": "Final answer", "iters": 2})

    rec = await orch_mod.create_run(1, "Write summary", worker_budget=2, max_revisions=0)
    run_id = rec["id"]

    out = await run_orchestrator_pipeline(chat, agent, 1, run_id)
    assert out.get("result") == "Final answer"
    assert out.get("approved") is True
    assert chat.chat.call_count == 2
    assert agent.run.call_count == 1

    final = await orch_mod.get_run(run_id)
    assert final is not None
    assert final["status"] == "done"
