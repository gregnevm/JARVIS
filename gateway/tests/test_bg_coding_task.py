"""CA-5.3 — gateway worker dispatch для coding_task job type."""
from __future__ import annotations

import asyncio

from app.bg_job_runner import run_bg_job_once


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


class _BaseTools:
    def __init__(self, result: dict) -> None:
        self._result = result
        self.finished: list[dict] = []
        self.ran: list[dict] = []

    async def dequeue_bg_job(self):
        return {
            "id": "c1",
            "user_id": 9,
            "type": "coding_task",
            "payload": {"exe": "pytest", "args": ["-k", "x"], "path": "/repo", "max_rounds": 2},
        }

    async def run_coding_task(self, job_id, uid, *, exe, args, path, task, max_rounds):
        self.ran.append(
            {"job_id": job_id, "uid": uid, "exe": exe, "args": args, "path": path, "max_rounds": max_rounds}
        )
        return self._result

    async def finish_bg_job(self, job_id, *, result="", error="", status="done"):
        self.finished.append({"id": job_id, "result": result, "error": error, "status": status})


def test_coding_task_dispatched_to_fix():
    tools = _BaseTools({"status": "fixed", "rounds": 1, "report": "✅ PASS"})
    tg = FakeTG()
    ok = asyncio.run(run_bg_job_once(tools, tg))
    assert ok is True
    # /agent/code/fix викликано з payload з черги (headless у самому ToolsClient)
    assert tools.ran[0]["exe"] == "pytest"
    assert tools.ran[0]["args"] == ["-k", "x"]
    assert tools.ran[0]["max_rounds"] == 2
    assert tools.finished[0]["status"] == "done"
    assert "fixed" in tools.finished[0]["result"]
    assert tg.sent[0][0] == 9 and "✅" in tg.sent[0][1]


def test_coding_task_policy_denied_is_done_not_failed():
    # policy_denied — легітимний результат (немає CODING_HEADLESS_APPLY), не infra-помилка.
    tools = _BaseTools({"status": "policy_denied", "rounds": 0, "report": "denied"})
    tg = FakeTG()
    asyncio.run(run_bg_job_once(tools, tg))
    assert tools.finished[0]["status"] == "done"
    assert "⚠️" in tg.sent[0][1]


def test_coding_task_error_marks_failed():
    tools = _BaseTools({"error": "boom"})
    tg = FakeTG()
    asyncio.run(run_bg_job_once(tools, tg))
    assert tools.finished[0]["status"] == "failed"
    assert "boom" in tools.finished[0]["error"]
