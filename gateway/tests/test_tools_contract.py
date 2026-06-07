"""Contract: ToolsClient HTTP paths ↔ Tools FastAPI routes."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_CLIENT = ROOT / "gateway" / "app" / "tools_client.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tools_routes.json"

_SKIP_TOOLS_PATHS = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}

# f-string path segment → FastAPI param name
_PATH_NORMALIZE = {
    "plan_id": "{plan_id}",
    "job_id": "{job_id}",
    "skill_id": "{skill_id}",
    "team_id": "{team_id}",
    "run_id": "{run_id}",
    "server_name": "{server_name}",
}


def _normalize_client_path(path: str) -> str:
    for var, template in _PATH_NORMALIZE.items():
        path = path.replace(f"{{{var}}}", template)
    return path


def _parse_tools_client_routes() -> set[tuple[str, str]]:
    text = TOOLS_CLIENT.read_text(encoding="utf-8")
    routes: set[tuple[str, str]] = set()

    for method, path in re.findall(
        r'self\._client\.(get|post|delete)\(\s*f"\{self\._base\}([^"]+)"',
        text,
        flags=re.IGNORECASE,
    ):
        routes.add((method.upper(), _normalize_client_path(path)))

    for method, path in re.findall(
        r'self\._request\(\s*"(GET|POST|DELETE)",\s*("[^"]+"|f"[^"]+")',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if path.startswith('f"'):
            path = path[2:-1]
        else:
            path = path.strip('"')
        routes.add((method.upper(), _normalize_client_path(path)))

    if 'self._client.post(\n                self._url' in text or "self._client.post(\n            self._url" in text:
        routes.add(("POST", "/agent"))
    if "self._stream_url" in text:
        routes.add(("POST", "/agent/stream"))

    # Multiline post with _url
    if re.search(r'self\._client\.post\([^)]*self\._url', text, re.DOTALL):
        routes.add(("POST", "/agent"))
    if re.search(r'self\._client\.stream\([^)]*self\._stream_url', text, re.DOTALL):
        routes.add(("POST", "/agent/stream"))

    return routes


def _collect_tools_app_routes() -> set[tuple[str, str]]:
    """Збирає routes з Tools app у subprocess (уникаємо clash `app` з gateway)."""
    import subprocess
    import sys

    script = """
import json, sys
sys.path.insert(0, "tools")
from app.main import app
skip = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
out = []
for route in app.routes:
    methods = getattr(route, "methods", None) or set()
    path = getattr(route, "path", None)
    if not path or not methods or path in skip:
        continue
    for method in methods:
        if method not in {"HEAD", "OPTIONS"}:
            out.append([method, path])
print(json.dumps(out))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout.strip())
    return {(m, p) for m, p in data}


@pytest.fixture(scope="module")
def client_routes() -> set[tuple[str, str]]:
    return _parse_tools_client_routes()


@pytest.fixture(scope="module")
def tools_routes() -> set[tuple[str, str]]:
    return _collect_tools_app_routes()


def test_tools_client_paths_exist_in_tools_app(client_routes, tools_routes):
    missing = sorted(client_routes - tools_routes)
    assert not missing, f"ToolsClient calls missing from Tools app: {missing}"


def test_fixture_snapshot_matches_client(client_routes):
    """Snapshot для diff при додаванні нових ToolsClient методів."""
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    serialized = sorted(f"{m} {p}" for m, p in client_routes)
    if FIXTURE.exists():
        saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert saved == serialized, (
            "tools_routes.json out of date — update fixture if ToolsClient paths changed intentionally"
        )
    else:
        FIXTURE.write_text(json.dumps(serialized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
