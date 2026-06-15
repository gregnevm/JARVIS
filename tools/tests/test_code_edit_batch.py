"""code_edit_batch (CA-4.3/4.4): schema gating, mutating/dry_run, transactional apply."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import computer, toolkit
from app.computer_confirm import describe_action, is_mutating, tier_for
from app.config import settings


def _edits() -> list[dict[str, Any]]:
    return [
        {"path": "/p/a.py", "old_string": "x", "new_string": "y"},
        {"path": "/p/b.py", "old_string": "m", "new_string": "n"},
    ]


# --- pure: mutating / tier / describe ---------------------------------------

def test_batch_mutating_unless_dry_run() -> None:
    assert is_mutating("code_edit_batch", {"edits": _edits()})
    assert not is_mutating("code_edit_batch", {"edits": _edits(), "dry_run": True})
    assert tier_for("code_edit_batch") == "T1"


def test_batch_describe_lists_files() -> None:
    desc = describe_action("code_edit_batch", {"edits": _edits()})
    assert "2 файл" in desc and "/p/a.py" in desc and "/p/b.py" in desc


def test_batch_describe_dry_run_marker() -> None:
    desc = describe_action("code_edit_batch", {"edits": _edits(), "dry_run": True})
    assert "[dry-run]" in desc


# --- schema gating -----------------------------------------------------------

def test_batch_schema_present_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "code_edit_batch" in names


def test_batch_schema_absent_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "code_edit_batch" not in names


# --- apply (mocked host-agent) ----------------------------------------------

def _patch_request(rv: dict[str, Any]) -> Any:
    return patch("app.computer._request", new_callable=AsyncMock, return_value=rv)


async def test_batch_impl_sends_normalized_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "ok", "count": 2, "results": [
        {"path": "/p/a.py", "occurrences": 1, "diff": "-x\n+y", "backup": "/p/.jarvis_backup/a.py.bak"},
        {"path": "/p/b.py", "occurrences": 1, "diff": "-m\n+n", "backup": "/p/.jarvis_backup/b.py.bak"},
    ]}
    with _patch_request(rv) as req:
        out = await computer._code_edit_batch_impl(_edits())
    sent = req.await_args.kwargs["json"]
    assert sent["dry_run"] is False and len(sent["edits"]) == 2
    assert sent["edits"][0]["mode"] == "search_replace"  # нормалізовано
    assert "Транзакційно застосовано 2" in out and "/p/a.py" in out and "/p/b.py" in out


async def test_batch_impl_dry_run_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "dry_run", "count": 1, "results": [
        {"path": "/p/a.py", "occurrences": 1, "diff": "-x\n+y"}]}
    with _patch_request(rv) as req:
        out = await computer._code_edit_batch_impl(_edits(), dry_run=True)
    assert req.await_args.kwargs["json"]["dry_run"] is True
    assert "Dry-run" in out


async def test_batch_impl_propagates_rollback_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    with _patch_request({"error": "hostagent HTTP 422: edit 1 (/p/b.py) failed: ...; rolled back 1 edit(s)"}):
        out = await computer._code_edit_batch_impl(_edits())
    assert "rolled back" in out


async def test_batch_impl_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    out = await computer._code_edit_batch_impl([])
    assert "порожній" in out.lower()


async def test_execute_internal_routes_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "ok", "count": 1, "results": [{"path": "/p/a.py", "occurrences": 1, "diff": "d"}]}
    with _patch_request(rv) as req:
        out = await computer.execute_internal(
            "code_edit_batch", {"edits": _edits(), "dry_run": False}, trusted=True
        )
    assert len(req.await_args.kwargs["json"]["edits"]) == 2
    assert "✅" in out


async def test_batch_denied_for_non_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    out = await toolkit.dispatch("code_edit_batch", {"edits": _edits()}, user_id=99)
    assert "власник" in out.lower()
