"""Computer Use: confirm flow, audit, mutating detection."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app import computer
from app.computer_confirm import (
    describe_action,
    execute_confirmed,
    is_mutating,
    load_origin,
    load_pending_raw,
    save_origin,
    save_pending,
    wrap_execute,
)
from app.config import settings


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture()
def confirm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_require_confirm", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1,7,42")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fake)
    monkeypatch.setattr(settings, "ps_whitelist", "Set-Content,Write-Output")
    return fake


def test_is_mutating_readonly_ps():
    assert not is_mutating("run_powershell", {"script": "Get-ChildItem C:\\"})
    assert is_mutating("run_powershell", {"script": "Set-Content x y"})
    assert is_mutating("fs_write", {"path": "C:\\x", "content": "a"})
    assert not is_mutating("fs_read", {"path": "C:\\x"})


def test_describe_action():
    assert "PowerShell" in describe_action("run_powershell", {"script": "dir"})


async def test_load_pending_raw_includes_script(confirm_env: FakeRedis):
    await save_pending(42, "run_powershell", {"script": "Set-Content x y"})
    raw = await load_pending_raw(42)
    assert raw["pending"] is True
    assert raw["tool"] == "run_powershell"
    assert raw["script"] == "Set-Content x y"
    assert "PowerShell" in raw["description"]
    assert raw["mutating"] is True


async def test_wrap_execute_returns_confirm_marker(confirm_env: FakeRedis):
    async def exec_fn() -> str:
        return "should not run"

    out = await wrap_execute(42, "fs_write", {"path": "C:\\a", "content": "x"}, exec_fn)
    assert "[[COMPUTER_CONFIRM:" in out
    assert confirm_env.store


async def test_wrap_execute_skips_confirm_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_require_confirm", False)
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")

    async def exec_fn() -> str:
        return "done"

    out = await wrap_execute(1, "fs_write", {"path": "x", "content": "y"}, exec_fn)
    assert out == "done"


async def test_save_load_origin(confirm_env: FakeRedis):
    from app import computer_confirm

    await computer_confirm.save_origin(7, "зроби скріншот")
    assert await load_origin(7) == "зроби скріншот"


async def test_execute_confirmed_returns_origin(confirm_env: FakeRedis, monkeypatch: pytest.MonkeyPatch):
    from app import computer_confirm

    await save_origin(7, "відкрий блокнот")
    code = await computer_confirm.save_pending(7, "fs_write", {"path": "C:\\t", "content": "hi"})
    monkeypatch.setattr(
        computer,
        "execute_internal",
        AsyncMock(return_value="Записано ✅"),
    )
    result, origin = await execute_confirmed(7, code)
    assert result == "Записано ✅"
    assert origin == "відкрий блокнот"


async def test_execute_confirmed_runs_action(confirm_env: FakeRedis, monkeypatch: pytest.MonkeyPatch):
    from app import computer_confirm

    code = await computer_confirm.save_pending(7, "fs_write", {"path": "C:\\t", "content": "hi"})
    mock_exec = AsyncMock(return_value="Записано ✅")
    monkeypatch.setattr(computer, "execute_internal", mock_exec)
    result, origin = await execute_confirmed(7, code)
    assert result == "Записано ✅"
    assert origin == ""
    mock_exec.assert_awaited_once()
    assert mock_exec.await_args.kwargs.get("trusted") is True
    log_path = Path(settings.data_dir) / "logs" / "computer.jsonl"
    assert log_path.is_file()


async def test_execute_confirmed_learns_ps(
    confirm_env: FakeRedis, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "computer_auto_learn_whitelist", True)
    monkeypatch.setattr(settings, "ps_whitelist", "")
    mock = AsyncMock(
        return_value={"stdout": "ok", "stderr": "", "code": 0},
    )
    with patch.object(computer, "_request", mock):
        from app import computer_confirm

        code = await computer_confirm.save_pending(
            7,
            "run_powershell",
            {"script": "Stop-Service -Name docker"},
        )
        result, _ = await execute_confirmed(7, code)
    assert "[exit 0]" in result
    from app.computer_learned import learned_ps

    assert "stop-service" in learned_ps()
