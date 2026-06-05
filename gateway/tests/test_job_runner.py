"""Job runner poller — due macros → Telegram."""
import asyncio

from app.job_runner import _run_due_jobs


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


class FakeTools:
    def __init__(self, jobs: list[dict], result: str = "ok") -> None:
        self._jobs = jobs
        self._result = result
        self.ran: list[tuple] = []

    async def due_jobs(self):
        return self._jobs

    async def run_macro(self, user_id, name):
        self.ran.append((user_id, name))
        return self._result


def _run(coro):
    return asyncio.run(coro)


def test_run_due_jobs_empty():
    n = _run(_run_due_jobs(FakeTools([], "ok"), FakeTG()))
    assert n == 0


def test_run_due_jobs_sends_result():
    tg = FakeTG()
    tools = FakeTools([{"user_id": 42, "macro": "stack-status"}], "compose ps ok")
    n = _run(_run_due_jobs(tools, tg))
    assert n == 1
    assert tools.ran == [(42, "stack-status")]
    assert tg.sent[0][0] == 42
    assert "stack-status" in tg.sent[0][1]


def test_run_due_jobs_skips_invalid():
    tg = FakeTG()
    tools = FakeTools([{"user_id": 0, "macro": ""}, {"user_id": 7, "macro": "deploy"}])
    n = _run(_run_due_jobs(tools, tg))
    assert n == 1
    assert tools.ran == [(7, "deploy")]
