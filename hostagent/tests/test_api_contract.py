"""Contract: FastAPI routes match tools hostagent_contract (без імпорту tools/main)."""
from __future__ import annotations

from pathlib import Path

import pytest
from app.main import app

_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "app"
    / "hostagent_contract.py"
)


def _load_routes() -> list[tuple[str, str]]:
    text = _CONTRACT.read_text(encoding="utf-8")
    routes: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("HostagentRoute("):
            # HostagentRoute("POST", "/powershell", ...)
            parts = line.replace("HostagentRoute(", "").rstrip("),").split(",")
            method = parts[0].strip().strip('"')
            path = parts[1].strip().strip('"')
            routes.append((method, path))
    return routes


def _route_keys() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        path = getattr(r, "path", None)
        if not path or not methods:
            continue
        for m in methods:
            if m in ("GET", "POST", "DELETE"):
                out.add((m, path))
    return out


@pytest.mark.parametrize("method,path", _load_routes())
def test_hostagent_exposes_contract_route(method: str, path: str):
    assert (method, path) in _route_keys(), f"missing {method} {path}"
