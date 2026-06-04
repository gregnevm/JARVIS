"""Computer Use: computer client, whitelist, schemas, dispatch."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import computer, toolkit
from app.agent import decide_mode
from app.config import settings


@pytest.fixture()
def computer_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_allow_admin", False)
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "hostagent_url", "http://host.test:8400")
    monkeypatch.setattr(settings, "ps_whitelist", "Get-ChildItem,Write-Output")
    monkeypatch.setattr(settings, "cli_whitelist", "git,echo")
    monkeypatch.setattr(settings, "fetch_max_chars", 100)
    monkeypatch.setattr(settings, "computer_timeout", 5.0)


def test_decide_mode_computer_forced():
    assert decide_mode("anything", "computer") == "computer"


def test_schemas_exclude_computer_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "run_powershell" not in names


def test_schemas_include_computer_when_enabled(computer_enabled: None):
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "run_powershell" in names
    assert "fs_write" in names


def test_schemas_computer_false_even_if_enabled(computer_enabled: None):
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=False)]
    assert "run_powershell" not in names


async def test_disabled_returns_message(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", False)
    assert "вимкнено" in await computer.run_powershell("Write-Output 1")


async def test_ps_whitelist_blocks(computer_enabled: None):
    out = await computer.run_powershell("Remove-Item x")
    assert "PS_WHITELIST" in out


async def test_ps_whitelist_multistatement(computer_enabled: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        settings,
        "ps_whitelist",
        "Stop-Service,Start-Service,Write-Output",
    )
    mock = AsyncMock(return_value={"stdout": "ok", "stderr": "", "code": 0})
    with patch.object(computer, "_request", mock):
        out = await computer.run_powershell("Stop-Service -Name docker; Start-Service -Name docker")
    assert "[exit 0]" in out
    assert "PS_WHITELIST" not in out


async def test_ps_whitelist_blocks_second_cmdlet(computer_enabled: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ps_whitelist", "Stop-Service,Write-Output")
    out = await computer.run_powershell("Stop-Service x; Remove-Item y")
    assert "remove-item" in out.lower()
    assert "PS_WHITELIST" in out


async def test_admin_blocked(computer_enabled: None):
    out = await computer.run_powershell("Write-Output 1", as_admin=True)
    assert "COMPUTER_ALLOW_ADMIN" in out


async def test_cli_whitelist_blocks(computer_enabled: None):
    out = await computer.run_cli("rm", ["-rf", "/"])
    assert "CLI_WHITELIST" in out


async def test_run_powershell_calls_hostagent(computer_enabled: None):
    mock = AsyncMock(return_value={"stdout": "ok", "stderr": "", "code": 0})
    with patch.object(computer, "_request", mock):
        out = await computer.run_powershell("Write-Output hi")
    assert out.startswith("ok")
    assert "[exit 0]" in out
    mock.assert_awaited_once()
    assert mock.await_args.args[0] == "POST"
    assert mock.await_args.args[1] == "/powershell"


async def test_output_truncation(computer_enabled: None):
    long_out = "x" * 200
    mock = AsyncMock(return_value={"stdout": long_out, "stderr": "", "code": 0})
    with patch.object(computer, "_request", mock):
        out = await computer.run_powershell("Write-Output x")
    assert "обрізано" in out


async def test_request_sends_token_header(computer_enabled: None):
    captured: dict[str, Any] = {}

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"stdout": "1", "stderr": "", "code": "0"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: Any):
            captured["headers"] = kwargs.get("headers")
            captured["url"] = url
            return FakeResp()

    with patch("app.computer.httpx.AsyncClient", return_value=FakeClient()):
        await computer.run_powershell("Write-Output 1")
    assert captured["headers"]["X-Hostagent-Token"] == "tok"
    assert captured["url"] == "http://host.test:8400/powershell"


async def test_dispatch_run_powershell(computer_enabled: None):
    with patch.object(computer, "run_powershell", AsyncMock(return_value="done")) as mock:
        out = await toolkit.dispatch("run_powershell", {"script": "Write-Output 1"})
    assert out == "done"
    mock.assert_awaited_once()
