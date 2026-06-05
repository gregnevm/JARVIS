"""Contract: tools computer paths ↔ hostagent_contract."""
from __future__ import annotations

import re
from pathlib import Path

from app.hostagent_contract import COMPUTER_SOURCE_PATHS, TOOLS_HOSTAGENT_ROUTES


def _paths_in_computer_py() -> set[str]:
    text = Path(__file__).resolve().parents[1] / "app" / "computer.py"
    raw = text.read_text(encoding="utf-8")
    return set(re.findall(r'["\'](/[^"\']+)["\']', raw))


def test_computer_py_uses_contract_paths():
    used = _paths_in_computer_py()
    host_paths = {r.path for r in TOOLS_HOSTAGENT_ROUTES}
    extra = used - host_paths
    assert not extra, f"computer.py paths not in contract: {extra}"


def test_contract_covers_computer_mutations():
    used = _paths_in_computer_py() - {"/health", "/health/stack"}
    missing = COMPUTER_SOURCE_PATHS - used
    assert not missing, f"contract paths unused in computer.py: {missing}"
