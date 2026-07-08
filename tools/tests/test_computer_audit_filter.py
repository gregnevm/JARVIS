"""Фільтр audit log по tool."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.computer_audit import execution_node, log_action, tail_actions
from app.config import settings


def test_tail_actions_filter_powershell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    log_action(1, "run_powershell", "T0", {"script": "Get-Service"}, "ok", confirmed=True)
    log_action(1, "fs_read", "T0", {"path": "C:\\x"}, "file", confirmed=True)
    log_action(1, "run_powershell", "T0", {"script": "docker ps"}, "list", confirmed=False)

    all_entries = tail_actions(limit=10)
    assert len(all_entries) == 3

    ps_only = tail_actions(limit=10, tool="run_powershell")
    assert len(ps_only) == 2
    assert all(e["tool"] == "run_powershell" for e in ps_only)


def test_execution_node_classifies_cross_node_vs_local():
    # крос-нодові (Windows-хост через hostagent): PS/FS, code_edit(_batch)→/fs/edit, screen/uia
    for tool in ("run_powershell", "fs_write", "code_edit", "code_edit_batch", "screen_click", "uia_invoke"):
        assert execution_node(tool) == "hostagent"
    # локальні (у tools-контейнері) і невідомі → local: browser_* (Playwright in-proc), calc
    for tool in ("browser_open", "browser_click", "browser_eval", "calc", "some_future_tool"):
        assert execution_node(tool) == "local"


def test_log_action_records_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    log_action(1, "code_edit", "T1", {"path": "a.py"}, "ok", confirmed=True)     # /fs/edit → hostagent
    log_action(1, "browser_open", "T2", {"url": "x"}, "ok", confirmed=True)       # in-proc → local
    entries = {e["tool"]: e for e in tail_actions(limit=10)}
    assert entries["code_edit"]["node"] == "hostagent"
    assert entries["browser_open"]["node"] == "local"


def test_log_action_redacts_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P0-7: секрети в args/result не лягають у computer.jsonl cleartext."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    secret = "sk-jarvis-ABCDEF0123456789ABCDEF0123456789"
    log_action(
        1,
        "run_cli",
        "T1",
        {"exe": "git", "args": f"clone https://x:{secret}@example.com/r"},
        f"token={secret} done",
        confirmed=True,
    )
    entry = tail_actions(limit=1)[0]
    blob = json.dumps(entry, ensure_ascii=False)
    assert secret not in blob  # відредаговано і в args, і в result_preview
