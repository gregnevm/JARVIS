"""Confirm flow: rate limit + admin second step."""
import pytest

from app.computer_confirm import (
    ADMIN_CONFIRM_MARKER,
    CONFIRM_MARKER,
    execute_confirmed,
    save_pending,
    wrap_execute,
)
from app.config import settings


class FakePipe:
    def __init__(self, redis: "FakeRedis") -> None:
        self._r = redis
        self._ops: list[tuple[str, str]] = []

    def incr(self, key: str) -> None:
        self._ops.append(("incr", key))

    def expire(self, key: str, sec: int) -> None:
        self._ops.append(("expire", key))

    async def execute(self) -> None:
        for op, key in self._ops:
            if op == "incr":
                self._r.counts[key] = self._r.counts.get(key, 0) + 1


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, val: str) -> None:
        self.store[key] = val

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def pipeline(self) -> FakePipe:
        return FakePipe(self)


@pytest.fixture
def redis_env(monkeypatch: pytest.MonkeyPatch):
    fr = FakeRedis()
    monkeypatch.setattr("app.computer_confirm._redis", fr)
    monkeypatch.setattr("app.computer_rate_limit._redis", fr)
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "computer_require_confirm", True)
    monkeypatch.setattr(settings, "computer_rate_limit_per_hour", 100)
    return fr


async def test_wrap_returns_confirm_marker(redis_env):
    async def _run() -> str:
        return "done"

    out = await wrap_execute(1, "fs_write", {"path": "/x", "content": "y"}, _run)
    assert CONFIRM_MARKER.split("{")[0] in out


async def test_admin_two_step_confirm(redis_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "admin_user_ids", "1")
    monkeypatch.setattr(settings, "computer_allow_admin", True)

    executed: list[str] = []

    async def _fake_internal(tool, args, *, trusted=False):
        executed.append(tool)
        return "admin-ok"

    monkeypatch.setattr("app.computer.execute_internal", _fake_internal)

    code = await save_pending(1, "run_powershell", {"script": "x", "as_admin": True})
    r1, _ = await execute_confirmed(1, code)
    assert ADMIN_CONFIRM_MARKER[:24] in r1
    assert not executed

    code2 = r1.split(":")[1].split("]")[0][:6]
    # parse code from marker [[COMPUTER_ADMIN_CONFIRM:xxxxxx]]
    import re

    m = re.search(r"COMPUTER_ADMIN_CONFIRM:([a-f0-9]+)", r1)
    assert m
    r2, _ = await execute_confirmed(1, m.group(1))
    assert r2 == "admin-ok"
    assert executed == ["run_powershell"]
