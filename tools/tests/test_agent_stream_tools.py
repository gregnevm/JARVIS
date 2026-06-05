"""Стрім агента: tool_start / tool_done для PowerShell Panel."""
from __future__ import annotations

from typing import Any

import pytest

from app.agent import AgentRunner
from app.config import settings


class FakeOllama:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    async def chat(self, model, messages, tools=None, num_predict=1024):  # noqa: ANN001
        return self._responses.pop(0)

    async def chat_stream(self, model, messages, num_predict=1024):  # noqa: ANN001
        return
        yield  # pragma: no cover


class FakeMemory:
    async def search(self, user_id, query, top_k=5, project_id=None):  # noqa: ANN001
        return []

    async def store(self, user_id, content, role="user", project_id=None):  # noqa: ANN001
        return

    async def history(self, user_id, limit=12):  # noqa: ANN001
        return []

    async def get_project(self, user_id, project_id):  # noqa: ANN001
        return None


async def test_run_stream_emits_tool_start_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_mode", "computer")
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")

    async def fake_dispatch(name, args, user_id, **kw):  # noqa: ANN001
        return "stdout line\n[exit 0]"

    monkeypatch.setattr("app.agent.dispatch", fake_dispatch)

    ollama = FakeOllama(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "run_powershell",
                            "arguments": {"script": "Get-Service docker"},
                        }
                    }
                ],
            },
            {"role": "assistant", "content": "Сервіс перевірено."},
        ]
    )
    events = [
        ev
        async for ev in AgentRunner(ollama, FakeMemory()).run_stream(
            1, "перевір docker", mode="computer"
        )
    ]
    starts = [e for e in events if "tool_start" in e]
    dones = [e for e in events if "tool_done" in e]
    assert len(starts) == 1
    assert starts[0]["tool_start"]["name"] == "run_powershell"
    assert starts[0]["tool_start"]["args"]["script"] == "Get-Service docker"
    assert len(dones) == 1
    assert "stdout line" in dones[0]["tool_done"]["result"]
