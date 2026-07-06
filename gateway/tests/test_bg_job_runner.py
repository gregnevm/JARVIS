"""Background job runner tests."""
from __future__ import annotations

import asyncio

from app.bg_job_runner import run_bg_job_once


class FakeTools:
    def __init__(self) -> None:
        self.finished: list[dict] = []

    async def dequeue_bg_job(self):
        return {
            "id": "j1",
            "user_id": 42,
            "payload": {"text": "hi", "mode": "chat"},
        }

    async def process(self, payload):
        return "answer text"

    async def finish_bg_job(self, job_id, *, result="", error="", status="done"):
        self.finished.append(
            {"id": job_id, "result": result, "error": error, "status": status}
        )


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


def test_run_bg_job_once():
    tools = FakeTools()
    tg = FakeTG()
    ok = asyncio.run(run_bg_job_once(tools, tg))
    assert ok is True
    assert tools.finished[0]["status"] == "done"
    assert tg.sent[0][0] == 42


class FakeToolsResearch:
    async def dequeue_bg_job(self):
        return {
            "id": "r1",
            "user_id": 7,
            "type": "deep_research",
            "payload": {"query": "topic", "max_hops": 2},
        }

    async def run_research(self, job_id, uid, query, max_hops):
        return {"report": "done report", "sources": []}

    async def finish_bg_job(self, job_id, *, result="", error="", status="done"):
        pass


def test_run_deep_research_job():
    tg = FakeTG()
    ok = asyncio.run(run_bg_job_once(FakeToolsResearch(), tg))
    assert ok is True
    assert tg.sent[0][0] == 7
