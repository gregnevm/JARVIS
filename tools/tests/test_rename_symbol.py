"""rename_symbol (CA-4.5): identifier-rename по репо через transactional batch."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import computer, toolkit
from app.computer_confirm import describe_action, is_mutating, tier_for
from app.config import settings


# --- pure: mutating / tier / describe ---------------------------------------

def test_rename_mutating_unless_dry_run() -> None:
    args = {"old_name": "User", "new_name": "Account", "root": "/repo"}
    assert is_mutating("rename_symbol", args)
    assert not is_mutating("rename_symbol", {**args, "dry_run": True})
    assert tier_for("rename_symbol") == "T1"


def test_rename_describe() -> None:
    desc = describe_action(
        "rename_symbol", {"old_name": "User", "new_name": "Account", "root": "/repo"}
    )
    assert "User" in desc and "Account" in desc and "/repo" in desc


# --- schema gating -----------------------------------------------------------

def test_rename_schema_present_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "rename_symbol" in names


# --- impl (mocked rg + batch) ------------------------------------------------

def _patch_request(rv: dict[str, Any]) -> Any:
    return patch("app.computer._request", new_callable=AsyncMock, return_value=rv)


def _patch_find(files: list[str], err: str = "") -> Any:
    return patch(
        "app.tools.coding_tools.find_symbol_files",
        new_callable=AsyncMock,
        return_value=(files, err),
    )


async def test_rename_builds_word_boundary_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    batch_rv = {"status": "ok", "count": 2, "results": [
        {"path": "/repo/a.py", "occurrences": 1, "diff": "-User\n+Account"},
        {"path": "/repo/b.py", "occurrences": 2, "diff": "-User\n+Account"},
    ]}
    with _patch_find(["/repo/a.py", "/repo/b.py"]), _patch_request(batch_rv) as req:
        out = await computer._rename_symbol_impl("User", "Account", "/repo")
    sent = req.await_args.kwargs["json"]
    assert sent["dry_run"] is False
    assert all(e["word_boundary"] and e["replace_all"] for e in sent["edits"])
    assert sent["edits"][0]["old_string"] == "User" and sent["edits"][0]["new_string"] == "Account"
    assert "rename User → Account у 2 файл" in out


async def test_rename_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    rv = {"status": "dry_run", "count": 1, "results": [{"path": "/repo/a.py", "occurrences": 1, "diff": "d"}]}
    with _patch_find(["/repo/a.py"]), _patch_request(rv) as req:
        out = await computer._rename_symbol_impl("User", "Account", "/repo", dry_run=True)
    assert req.await_args.kwargs["json"]["dry_run"] is True
    assert "Dry-run" in out


async def test_rename_rejects_non_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    out = await computer._rename_symbol_impl("a.b", "c", "/repo")
    assert "ідентифікатор" in out


async def test_rename_rejects_same_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    out = await computer._rename_symbol_impl("User", "User", "/repo")
    assert "однакові" in out


async def test_rename_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    with _patch_find([]):
        out = await computer._rename_symbol_impl("Nope", "X", "/repo")
    assert "не знайдено" in out


async def test_rename_denied_for_non_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    out = await toolkit.dispatch(
        "rename_symbol", {"old_name": "User", "new_name": "Account", "root": "/repo"}, user_id=99
    )
    assert "власник" in out.lower()
