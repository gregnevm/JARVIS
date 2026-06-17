"""TC-5 — delegate_tick bg handler (daily brief, S4 read-only notify)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.bg_job_runner import run_bg_job_once


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


class FakeTools:
    def __init__(self, brief: str = "усе спокійно") -> None:
        self._brief = brief
        self.finished: list[dict] = []
        self.processed: list[dict] = []

    async def dequeue_bg_job(self):
        return {
            "id": "d1", "user_id": 7, "type": "delegate_tick",
            "payload": {"principal_id": "7", "org_id": "o", "cursor": ""},
        }

    async def process(self, payload):
        self.processed.append(payload)
        return self._brief

    async def finish_bg_job(self, job_id, *, result="", error="", status="done"):
        self.finished.append({"id": job_id, "result": result, "status": status})


def test_delegate_tick_briefs_and_notifies():
    tools = FakeTools()
    tg = FakeTG()
    ok = asyncio.run(run_bg_job_once(tools, tg))
    assert ok is True
    assert tools.finished[0]["status"] == "done"
    assert tools.processed[0]["mode"] == "agent"  # read-only reasoning turn
    assert tg.sent and "daily brief" in tg.sent[0][1]


def test_delegate_tick_failure_marks_failed():
    tools = FakeTools()
    tools.process = AsyncMock(side_effect=RuntimeError("boom"))
    tg = FakeTG()
    asyncio.run(run_bg_job_once(tools, tg))
    assert tools.finished[0]["status"] == "failed"
