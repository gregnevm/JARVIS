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
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr("app.computer_confirm._redis", fake)
    monkeypatch.setattr(settings, "ps_whitelist", "Set-Content,Write-Output")
    return fake


def test_is_mutating_readonly_ps():
    assert not is_mutating("run_powershell", {"script": "Get-ChildItem C:\\"})
    assert is_mutating("run_powershell", {"script": "Set-Content x y"})
    assert is_mutating("fs_write", {"path": "C:\\x", "content": "a"})
    assert not is_mutating("fs_read", {"path": "C:\\x"})


def test_describe_action():
    assert "PowerShell" in describe_action("run_powershell", {"script": "dir"})


async def test_wrap_execute_returns_confirm_marker(confirm_env: FakeRedis):
    async def exec_fn() -> str:
        return "should not run"

    out = await wrap_execute(42, "fs_write", {"path": "C:\\a", "content": "x"}, exec_fn)
    assert "[[COMPUTER_CONFIRM:" in out
    assert confirm_env.store


async def test_wrap_execute_skips_confirm_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_require_confirm", False)

    async def exec_fn() -> str:
        return "done"

    out = await wrap_execute(1, "fs_write", {"path": "x", "content": "y"}, exec_fn)
    assert out == "done"


async def test_execute_confirmed_runs_action(confirm_env: FakeRedis, monkeypatch: pytest.MonkeyPatch):
    from app import computer_confirm

    code = await computer_confirm.save_pending(7, "fs_write", {"path": "C:\\t", "content": "hi"})
    monkeypatch.setattr(
        computer,
        "execute_internal",
        AsyncMock(return_value="Записано ✅"),
    )
    result = await execute_confirmed(7, code)
    assert result == "Записано ✅"
    log_path = Path(settings.data_dir) / "logs" / "computer.jsonl"
    assert log_path.is_file()
