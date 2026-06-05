"""Фільтр audit log по tool."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.computer_audit import log_action, tail_actions
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
