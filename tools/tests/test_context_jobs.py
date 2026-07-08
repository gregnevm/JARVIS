"""Виконавець context-jobs (tools): run_context_job + ручний роут /context/jobs/*.

Фейкові memory+chat — без мережі/Ollama. Доменна логіка вже покрита в
jarvis_core/tests/test_passport_jobs.py; тут — інтеграція адаптера+summarizer+dispatch."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from app.context_jobs import run_context_job
from app.main import app


class FakeMemory:
    def __init__(self) -> None:
        self.updated: list[tuple] = []
        self.ingested: list[dict] = []
        self.purged: list[tuple] = []

    async def context_pending(self, user_id: int, limit: int) -> list[dict]:
        return [{"id": 5, "summary": "excerpt", "tags": ["kind:worklog", "pending:summary"],
                 "payload": {"raw": "сирий текст для дозведення"}}]

    async def context_recent(self, user_id, limit, kind=None, tags=None) -> list[dict]:
        return [{"id": 9, "summary": "купив молоко", "tags": ["kind:note"]}]

    async def context_update(self, event_db_id, user_id, summary, tags, kind) -> dict:
        self.updated.append((event_db_id, summary, tags, kind))
        return {"ok": True}

    async def context_ingest(self, store: dict) -> dict:
        self.ingested.append(store)
        return {"id": 1, "inserted": True}

    async def context_purge(self, user_id, before=None, kind=None) -> int:
        self.purged.append((before, kind))
        return 1


class FakeChat:
    async def chat(self, model, messages, **kw) -> dict:
        return {"role": "assistant", "content": "СТИСЛИЙ ПІДСУМОК"}


_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)


# --- run_context_job dispatch ---

async def test_run_summarize_upgrades_pending():
    mem = FakeMemory()
    out = await run_context_job("context_summarize", mem, FakeChat(), 42,
                                day="2026-06-16", now=_NOW)
    assert out["summarized"] == 1
    eid, summary, tags, kind = mem.updated[0]
    assert eid == 5 and summary == "СТИСЛИЙ ПІДСУМОК"
    assert "pending:summary" not in tags and kind == "worklog"


async def test_run_daily_ingests_aggregate():
    mem = FakeMemory()
    out = await run_context_job("context_daily", mem, FakeChat(), 42,
                                day="2026-06-16", now=_NOW)
    assert out["created"] is True
    daily = mem.ingested[0]
    assert daily["kind"] == "daily" and daily["event_id"] == "daily:42:2026-06-16"


async def test_run_retention_purges_by_policy():
    mem = FakeMemory()
    out = await run_context_job("context_retention", mem, FakeChat(), 42,
                                day="2026-06-16", now=_NOW)
    assert out["total"] == len(out["purged"])  # 1 на kind
    assert "sms" in out["purged"]


async def test_run_proposal_ingests_proposals():
    mem = FakeMemory()
    out = await run_context_job("context_proposal", mem, FakeChat(), 42,
                                day="2026-06-16", now=_NOW)
    assert out["count"] >= 1
    assert mem.ingested[0]["kind"] == "proposal"


async def test_run_distill_ingests_facts_with_provenance():
    mem = FakeMemory()
    out = await run_context_job("context_distill", mem, FakeChat(), 42,
                                day="2026-06-16", now=_NOW)
    assert out["count"] >= 1
    rec = mem.ingested[0]
    assert rec["kind"] == "distilled"
    assert rec["payload"]["source_passport_ids"] == ["9"]   # provenance із recent-паспорта


async def test_run_unknown_job_raises():
    with pytest.raises(ValueError, match="unknown context job"):
        await run_context_job("bogus", FakeMemory(), FakeChat(), 1, day="d", now=_NOW)


# --- ручний роут (ASGITransport, без lifespan — app.state вручну) ---

@pytest.fixture()
def client():
    app.state.memory = FakeMemory()
    app.state.chat_backend = FakeChat()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_route_runs_retention(client):
    async with client as c:
        r = await c.post("/context/jobs/context_retention", params={"user_id": 42})
    assert r.status_code == 200
    assert r.json()["job"] == "context_retention"


async def test_route_unknown_job_404(client):
    async with client as c:
        r = await c.post("/context/jobs/bogus", params={"user_id": 42})
    assert r.status_code == 404
