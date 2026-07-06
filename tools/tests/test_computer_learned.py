"""Автоматичний whitelist після підтвердження."""
from __future__ import annotations

from pathlib import Path

import pytest
from app.computer_confirm import is_mutating
from app.computer_learned import (
    effective_ps_allowed,
    learn_from_action,
    learned_ps,
)
from app.config import settings


def test_learn_adds_ps_cmdlet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "computer_auto_learn_whitelist", True)
    learn_from_action("run_powershell", {"script": "Stop-Service -Name docker"})
    assert "stop-service" in learned_ps()
    assert "stop-service" in effective_ps_allowed()


def test_trusted_ps_skips_confirm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "computer_auto_learn_whitelist", True)
    monkeypatch.setattr(settings, "computer_auto_trust_learned", True)
    monkeypatch.setattr(settings, "ps_whitelist", "")
    learn_from_action("run_powershell", {"script": "Stop-Service x"})
    assert not is_mutating("run_powershell", {"script": "Stop-Service -Name docker"})
