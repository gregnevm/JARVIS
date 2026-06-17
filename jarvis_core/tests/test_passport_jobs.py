"""Context maintenance jobs (summarize/daily/retention) — оркестрування з фейками."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from jarvis_core.passport import build_daily, build_proposals, run_retention, summarize_pending


class FakeStore:
    """In-memory фейк ContextStore — фіксує виклики, без мережі/БД."""

    def __init__(self, pending: list[dict] | None = None, recent: list[dict] | None = None) -> None:
        self._pending = pending or []
        self._recent = recent or []
        self.updated: list[dict[str, Any]] = []
        self.ingested: list[dict[str, Any]] = []
        self.purged: list[dict[str, Any]] = []

    async def pending(self, user_id: int, limit: int) -> list[dict]:
        return self._pending[:limit]

    async def update(self, event_db_id, user_id, *, summary, tags, kind) -> dict:
        self.updated.append({"id": event_db_id, "summary": summary, "tags": tags, "kind": kind})
        return {"ok": True}

    async def recent(self, user_id, limit, *, kind=None, tags=None) -> list[dict]:
        return self._recent[:limit]

    async def ingest(self, store: dict) -> dict:
        self.ingested.append(store)
        return {"id": 1, "inserted": True}

    async def purge(self, user_id, *, before=None, kind=None) -> int:
        self.purged.append({"before": before, "kind": kind})
        return 1


async def _summarizer(text: str) -> str:
    return f"SUMMARY({len(text)})"


# --- context_summarize ---

async def test_summarize_pending_upgrades_and_drops_tag():
    store = FakeStore(pending=[
        {"id": 7, "summary": "excerpt", "tags": ["kind:worklog", "pending:summary"],
         "payload": {"raw": "довгий сирий текст"}},
    ])
    n = await summarize_pending(store, _summarizer, user_id=42)
    assert n == 1
    upd = store.updated[0]
    assert upd["id"] == 7
    assert upd["summary"].startswith("SUMMARY")
    assert "pending:summary" not in upd["tags"]   # тег знято
    assert upd["kind"] == "worklog"               # kind збережено з тегів


async def test_summarize_pending_skips_empty_raw():
    store = FakeStore(pending=[{"id": 1, "summary": "", "tags": ["pending:summary"], "payload": {}}])
    assert await summarize_pending(store, _summarizer, user_id=1) == 0
    assert store.updated == []


# --- context_daily ---

async def test_build_daily_aggregates_into_one_passport():
    store = FakeStore(recent=[
        {"summary": "купив молоко", "tags": ["kind:note"]},
        {"summary": "дзвінок мамі", "tags": ["kind:call"]},
    ])
    res = await build_daily(store, _summarizer, 42, day="2026-06-16")
    assert res is not None
    daily = store.ingested[0]
    assert daily["kind"] == "daily"
    assert daily["event_id"] == "daily:42:2026-06-16"   # ідемпотентність
    assert "kind:daily" in daily["tags"] and "day:2026-06-16" in daily["tags"]


async def test_build_daily_excludes_prior_daily_and_noop_when_empty():
    store = FakeStore(recent=[{"summary": "вчора", "tags": ["kind:daily"]}])
    assert await build_daily(store, _summarizer, 1, day="2026-06-16") is None
    assert store.ingested == []


# --- context_proposal ---

async def _proposer(text: str) -> str:
    return "1. Передзвонити мамі\n- Оплатити рахунок\n• Відповісти Орестові"


async def test_build_proposals_ingests_kind_proposal():
    store = FakeStore(recent=[{"summary": "мама дзвонила", "tags": ["kind:call"]}])
    out = await build_proposals(store, _proposer, 42, max_n=3)
    assert out == ["Передзвонити мамі", "Оплатити рахунок", "Відповісти Орестові"]  # маркери зрізано
    assert len(store.ingested) == 3
    assert store.ingested[0]["kind"] == "proposal"
    assert "status:offered" in store.ingested[0]["tags"]


async def test_build_proposals_noop_when_only_proposals_or_daily():
    store = FakeStore(recent=[{"summary": "стара", "tags": ["kind:proposal"]}])
    assert await build_proposals(store, _proposer, 1) == []
    assert store.ingested == []


# --- context_retention ---

async def test_run_retention_purges_each_kind_with_cutoff():
    store = FakeStore()
    now = datetime(2026, 6, 16, 12, 0, 0)
    out = await run_retention(store, 42, now=now, policy={"sms": 30, "usage": 7})
    assert out == {"sms": 1, "usage": 1}
    kinds = {p["kind"] for p in store.purged}
    assert kinds == {"sms", "usage"}
    # cutoff = now - TTL (usage 7д → 2026-06-09)
    usage = next(p for p in store.purged if p["kind"] == "usage")
    assert usage["before"].startswith("2026-06-09")
