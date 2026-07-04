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


@pytest.mark.parametrize(
    "text,expected",
    [
        # regression: "APPROVED" is a substring of these rejections — must NOT parse as approval
        ("DISAPPROVED: has factual errors", False),
        ("UNAPPROVED — incomplete", False),
        ("disapproved (lowercase)", False),
        ("REJECTED", False),
        ("Rejection: the draft invents a source", False),
        ("NOT APPROVED: missing data", False),
        ("CHANGES REQUESTED before this can ship", False),
        # genuine approvals still parse as approval
        ("APPROVED", True),
        ("APPROVED with minor nits", True),
        ("Looks good, approved.", True),
        # incidental reject-words inside an approving verdict must NOT flip it (word-boundary approve
        # + literal "NOT APPROVED" guard only — no over-broad reject scan)
        ("APPROVED. The draft rejects the null hypothesis correctly.", True),
        ("Approved. No changes requested.", True),
        # an unparseable / empty verdict fails closed (not approved)
        ("", False),
        ("hmm, unclear", False),
    ],
)
def test_parse_critic_text_fallback_rejection_first(text: str, expected: bool):
    assert parse_critic_verdict(text)["approved"] is expected


def test_parse_critic_json_authoritative_over_prose():
    # JSON verdict wins even when prose keywords would say otherwise
    assert parse_critic_verdict('{"approved": false} — APPROVED')["approved"] is False
    assert parse_critic_verdict('{"approved": true} DISAPPROVED')["approved"] is True


@pytest.mark.asyncio
async def test_orchestrator_prose_disapproval_triggers_revision(monkeypatch: pytest.MonkeyPatch):
    """A Critic that rejects in prose ("DISAPPROVED …") must NOT be parsed as approval.

    On the pre-fix code the round-1 rejection parsed as approved=True and the loop shipped the
    unreviewed draft after a single worker round. With the fix the loop runs a second revision
    round and only stops when the Critic actually approves.
    """
    from app import orchestrator as orch_mod
    from app import redis_store

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

    fake = FakeRedis()
    monkeypatch.setattr(redis_store, "get_redis", lambda: fake)

    chat = AsyncMock()
    chat.chat = AsyncMock(
        side_effect=[
            {"content": "Plan: step 1"},
            {"content": "DISAPPROVED: the draft invents a citation."},  # round 1 — prose rejection
            {"content": '{"approved": true, "issues": [], "feedback": "ok"}'},  # round 2 — approved
        ]
    )
    agent = AsyncMock()
    agent.run = AsyncMock(
        side_effect=[
            {"text": "Draft with a bad citation", "iters": 2},
            {"text": "Corrected final answer", "iters": 2},
        ]
    )

    rec = await orch_mod.create_run(1, "Write summary", worker_budget=2, max_revisions=1)
    out = await run_orchestrator_pipeline(chat, agent, 1, rec["id"])

    # the prose "DISAPPROVED" forced a second worker round rather than shipping round-1 output
    assert agent.run.call_count == 2
    assert chat.chat.call_count == 3
    assert out.get("approved") is True
    assert out.get("result") == "Corrected final answer"


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
