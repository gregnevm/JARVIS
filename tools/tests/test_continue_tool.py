"""Continue.dev tool: schemas, dispatch, API client."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import toolkit
from app.config import settings
from app.tools import continue_tool


@pytest.fixture()
def continue_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_continue_dev", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "continue_dev_url", "http://continue.test:65432")
    monkeypatch.setattr(settings, "continue_dev_timeout", 5.0)
    monkeypatch.setattr(settings, "fetch_max_chars", 500)


def test_schema_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_continue_dev", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "continue_dev" not in names


def test_schema_in_computer_mode_when_enabled(continue_enabled: None) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "continue_dev" in names


async def test_disabled_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_continue_dev", False)
    out = await continue_tool.run("get_status")
    assert "ENABLE_CONTINUE_DEV=false" in out


async def test_open_file_requires_path(continue_enabled: None) -> None:
    out = await continue_tool.run("open_file", user_id=1)
    assert "path" in out.lower()


async def test_open_file_denied_for_non_owner(continue_enabled: None) -> None:
    out = await continue_tool.run("open_file", path=r"O:\JARVIS", user_id=99)
    assert "власник" in out.lower()


async def test_open_file_calls_hostagent_cli(continue_enabled: None) -> None:
    with patch(
        "app.computer._run_cli_impl",
        new_callable=AsyncMock,
        return_value="opened\n[exit 0]",
    ) as mock_cli:
        out = await continue_tool.run("open_file", path=r"O:\JARVIS\README.md", user_id=1)
    mock_cli.assert_awaited_once_with("code", [r"O:\JARVIS\README.md"], None, trusted=True)
    assert "Відкрито" in out


async def test_get_status_success(continue_enabled: None) -> None:
    state = {
        "isProcessing": False,
        "queueLength": 0,
        "session": {
            "history": [
                {"message": {"role": "assistant", "content": "Готово"}},
            ],
        },
    }

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return state

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> FakeResp:
            assert url.endswith("/state")
            return FakeResp()

    with patch("app.tools.continue_tool.httpx.AsyncClient", return_value=FakeClient()):
        out = await continue_tool.run("get_status")
    assert "isProcessing=False" in out
    assert "Готово" in out


async def test_send_prompt_polls_response(continue_enabled: None) -> None:
    states = [
        {"isProcessing": True, "queueLength": 1, "session": {"history": []}},
        {
            "isProcessing": False,
            "queueLength": 0,
            "session": {
                "history": [
                    {"message": {"role": "user", "content": "fix bug"}},
                    {"message": {"role": "assistant", "content": "Fixed imports."}},
                ],
            },
        },
    ]
    state_iter = iter(states)

    class FakeResp:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> FakeResp:
            return FakeResp(next(state_iter, states[-1]))

        async def post(self, url: str, json: dict) -> FakeResp:  # noqa: A002
            assert url.endswith("/message")
            assert json["message"] == "fix bug"
            return FakeResp({"queued": True, "position": 1})

    with patch("app.tools.continue_tool.httpx.AsyncClient", return_value=FakeClient()):
        with patch("app.tools.continue_tool.asyncio.sleep", new_callable=AsyncMock):
            out = await continue_tool.run("send_prompt", prompt="fix bug")
    assert out == "Fixed imports."


async def test_dispatch_continue_dev(continue_enabled: None) -> None:
    with patch(
        "app.tools.continue_tool.run",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_run:
        out = await toolkit.dispatch("continue_dev", {"action": "get_status"}, user_id=1)
    mock_run.assert_awaited_once()
    assert out == "ok"
