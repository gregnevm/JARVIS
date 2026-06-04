"""resume_after_computer — промпт з origin + другий хід агента."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.agent_turn import resume_after_computer


class FakeTG:
    async def send_chat_action(self, chat_id, action):
        pass


class FakeTools:
    pass


def _run(coro):
    return asyncio.run(coro)


def test_resume_after_computer_includes_origin_in_payload():
    tg = FakeTG()
    tools = FakeTools()
    captured: list[dict] = []

    async def fake_turn(_tg, _tools, _chat_id, payload, *_a, **_kw):
        captured.append(payload)
        return "готово"

    with patch("app.agent_turn.run_agent_turn", new=AsyncMock(side_effect=fake_turn)):
        out = _run(
            resume_after_computer(
                tg,
                tools,
                100,
                7,
                "Файл записано ✅",
                None,
                origin_text="зроби скріншот",
                message_thread_id=99,
            )
        )
    assert out == "готово"
    payload = captured[0]
    assert "зроби скріншот" in payload["text"]
    assert "Файл записано" in payload["text"]
    assert payload["type"] == "computer_resume"
    assert payload["message_thread_id"] == 99
