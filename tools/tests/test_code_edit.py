"""code_edit (CA-1.2): schema gating, mutating/confirm flow, apply via host-agent."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app import computer, toolkit
from app.computer_confirm import (
    CONFIRM_MARKER,
    describe_action,
    execute_confirmed,
    is_mutating,
    tier_for,
)
from app.config import settings

# --- pure: mutating / tier / describe ---------------------------------------

def test_code_edit_is_mutating() -> None:
    assert is_mutating("code_edit", {"path": "/x", "old_string": "a", "new_string": "b"})
    assert tier_for("code_edit") == "T1"


def test_describe_action_search_replace_shows_diff() -> None:
    desc = describe_action(
        "code_edit",
        {"path": "/p/f.py", "old_string": "return 1", "new_string": "return 2"},
    )
    assert "/p/f.py" in desc
    assert "- return 1" in desc and "+ return 2" in desc


def test_describe_action_diff_mode() -> None:
    desc = describe_action("code_edit", {"path": "/p/f.py", "mode": "diff", "diff": "@@ -1 +1 @@"})
    assert "[diff]" in desc


# --- schema gating -----------------------------------------------------------

def test_schema_present_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "code_edit" in names


def test_schema_absent_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "code_edit" not in names


# --- apply (mocked host-agent) ----------------------------------------------

def _patch_request(rv: dict[str, Any]) -> Any:
    return patch("app.computer._request", new_callable=AsyncMock, return_value=rv)


async def test_code_edit_impl_sends_payload_and_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"path": "/p/f.py", "status": "ok", "occurrences": 1,
          "backup": "/p/.jarvis_backup/f.py.bak", "diff": "-return 1\n+return 2"}
    with _patch_request(rv) as req:
        out = await computer._code_edit_impl(
            "/p/f.py", old_string="return 1", new_string="return 2"
        )
    sent = req.await_args.kwargs["json"]
    assert sent["mode"] == "search_replace" and sent["path"] == "/p/f.py"
    assert sent["old_string"] == "return 1" and sent["new_string"] == "return 2"
    assert "✅" in out and "```diff" in out and ".jarvis_backup" in out


async def test_code_edit_impl_propagates_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    with _patch_request({"error": "hostagent HTTP 422: old_string not unique"}):
        out = await computer._code_edit_impl("/p/f.py", old_string="x", new_string="y")
    assert "not unique" in out


async def test_execute_internal_routes_code_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    with _patch_request({"path": "/p/f.py", "occurrences": 1, "diff": "d", "backup": "b"}) as req:
        out = await computer.execute_internal(
            "code_edit",
            {"path": "/p/f.py", "old_string": "a", "new_string": "b"},
            trusted=True,
        )
    assert req.await_args.kwargs["json"]["path"] == "/p/f.py"
    assert "✅" in out


# --- confirm flow (Redis-backed) --------------------------------------------

class _FakePipe:
    def __init__(self, r: "_FakeRedis") -> None:
        self._r = r

    def incr(self, key: str) -> None:
        self._r.counts[key] = self._r.counts.get(key, 0) + 1

    def expire(self, key: str, sec: int) -> None:
        return None

    async def execute(self) -> None:
        return None


class _FakeRedis:
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

    def pipeline(self) -> "_FakePipe":
        return _FakePipe(self)


@pytest.fixture
def redis_env(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fr = _FakeRedis()
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fr)
    monkeypatch.setattr("app.computer_rate_limit.get_redis", lambda: fr)
    monkeypatch.setattr("app.computer_trust.get_redis", lambda: fr)
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "computer_require_confirm", True)
    monkeypatch.setattr(settings, "computer_rate_limit_per_hour", 100)
    return fr


async def test_code_edit_requires_confirm_then_applies(redis_env: _FakeRedis) -> None:
    # Крок 1: мутуюча дія → маркер підтвердження, БЕЗ виклику host-agent.
    with _patch_request({"path": "/p/f.py", "occurrences": 1, "diff": "d", "backup": "b"}) as req:
        out = await computer.code_edit(
            "/p/f.py", old_string="a", new_string="b", user_id=1
        )
        assert CONFIRM_MARKER.split("{")[0] in out
        assert req.await_count == 0  # ще не застосовано

        code = out.split("COMPUTER_CONFIRM:")[1].split("]]")[0]
        # Крок 2: підтвердження → застосування.
        result, _origin = await execute_confirmed(1, code.strip())
    assert "✅" in result


async def test_code_edit_denied_for_non_owner(redis_env: _FakeRedis) -> None:
    out = await toolkit.dispatch(
        "code_edit",
        {"path": "/p/f.py", "old_string": "a", "new_string": "b"},
        user_id=99,
    )
    assert "власник" in out.lower()


# --- code_edit_batch (CA-4.3/4.4) -------------------------------------------

def test_code_edit_batch_mutating_unless_dry_run() -> None:
    edits = [{"path": "/a", "old_string": "a", "new_string": "b"}]
    assert is_mutating("code_edit_batch", {"edits": edits})
    assert not is_mutating("code_edit_batch", {"edits": edits, "dry_run": True})
    assert tier_for("code_edit_batch") == "T1"


def test_describe_action_batch_lists_paths() -> None:
    desc = describe_action(
        "code_edit_batch",
        {"edits": [{"path": "/p/a.py"}, {"path": "/p/b.py"}]},
    )
    assert "2 файл" in desc and "/p/a.py" in desc and "/p/b.py" in desc


def test_code_edit_batch_schema_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "code_edit_batch" in names


async def test_code_edit_batch_impl_sends_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "ok", "count": 2, "edits": [
        {"path": "/a.py", "diff": "-x\n+X"}, {"path": "/b.py", "diff": "-y\n+Y"}]}
    edits = [
        {"path": "/a.py", "old_string": "x", "new_string": "X"},
        {"path": "/b.py", "old_string": "y", "new_string": "Y"},
    ]
    with _patch_request(rv) as req:
        out = await computer._code_edit_batch_impl(edits, dry_run=False)
    sent = req.await_args.kwargs["json"]
    assert sent["dry_run"] is False and len(sent["edits"]) == 2
    assert "Транзакційно застосовано 2" in out and "```diff" in out


async def test_code_edit_batch_dry_run_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "dry_run", "count": 1, "edits": [{"path": "/a.py", "diff": "-x\n+X"}]}
    with _patch_request(rv):
        out = await computer._code_edit_batch_impl(
            [{"path": "/a.py", "old_string": "x", "new_string": "X"}], dry_run=True
        )
    assert "Dry-run" in out


async def test_code_edit_batch_dry_run_no_confirm_applies(redis_env: _FakeRedis) -> None:
    # dry_run не мутуючий → одразу виконується без маркера підтвердження.
    rv = {"status": "dry_run", "count": 1, "edits": [{"path": "/a.py", "diff": "-x\n+X"}]}
    with _patch_request(rv) as req:
        out = await computer.code_edit_batch(
            [{"path": "/a.py", "old_string": "x", "new_string": "X"}],
            dry_run=True,
            user_id=1,
        )
    assert "COMPUTER_CONFIRM" not in out
    assert req.await_count == 1 and "Dry-run" in out


async def test_code_edit_batch_requires_confirm_when_writing(redis_env: _FakeRedis) -> None:
    with _patch_request({"status": "ok", "count": 1, "edits": []}) as req:
        out = await computer.code_edit_batch(
            [{"path": "/a.py", "old_string": "x", "new_string": "X"}],
            user_id=1,
        )
    assert CONFIRM_MARKER.split("{")[0] in out
    assert req.await_count == 0  # запис відкладено до підтвердження


async def test_code_edit_batch_denied_for_non_owner(redis_env: _FakeRedis) -> None:
    out = await toolkit.dispatch(
        "code_edit_batch",
        {"edits": [{"path": "/a.py", "old_string": "a", "new_string": "b"}]},
        user_id=99,
    )
    assert "власник" in out.lower()
