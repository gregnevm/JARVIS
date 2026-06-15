"""Regression: усі Tools REST endpoints після розбиття main.py."""
from __future__ import annotations

from app.main import app

EXPECTED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("GET", "/status"),
    ("GET", "/dashboard"),
    ("POST", "/mode"),
    ("DELETE", "/mode"),
    ("POST", "/tool/dispatch"),
    ("POST", "/calc"),
    ("POST", "/web_fetch"),
    ("POST", "/search"),
    ("POST", "/parse_file"),
    ("POST", "/code_exec"),
    ("POST", "/agent"),
    ("POST", "/agent/stream"),
    ("POST", "/agent/plan"),
    ("POST", "/agent/code/plan"),
    ("POST", "/agent/code/review"),
    ("GET", "/agent/plan/{plan_id}"),
    ("GET", "/agent/plans"),
    ("POST", "/agent/plan/{plan_id}/approve"),
    ("POST", "/agent/plan/{plan_id}/deny"),
    ("POST", "/agent/plan/{plan_id}/execute"),
    ("POST", "/computer/confirm"),
    ("POST", "/computer/cancel"),
    ("POST", "/computer/screenshot"),
    ("POST", "/computer/file/pull"),
    ("POST", "/computer/file/push"),
    ("POST", "/computer/clipboard/read"),
    ("POST", "/computer/see"),
    ("GET", "/computer/macros"),
    ("POST", "/computer/macro/run"),
    ("POST", "/computer/trust"),
    ("DELETE", "/computer/trust"),
    ("GET", "/computer/trust/status"),
    ("GET", "/computer/pending"),
    ("GET", "/computer/audit"),
    ("GET", "/computer/powershell/policy"),
    ("GET", "/computer/learned"),
    ("GET", "/reminders/ics"),
    ("GET", "/dataset/stats"),
    ("POST", "/dataset/export/mark"),
    ("POST", "/dataset/export/sharegpt"),
    ("GET", "/tasks"),
    ("DELETE", "/tasks"),
    ("GET", "/jobs"),
    ("GET", "/jobs/due"),
    ("POST", "/bgjobs"),
    ("POST", "/research"),
    ("POST", "/research/run"),
    ("GET", "/mcp/servers"),
    ("GET", "/mcp/{server_name}/tools"),
    ("POST", "/mcp/call"),
    ("GET", "/connectors/status"),
    ("GET", "/skills"),
    ("GET", "/skills/{skill_id}"),
    ("POST", "/skills/active"),
    ("GET", "/skills/active/{user_id}"),
    ("POST", "/subagents/spawn"),
    ("GET", "/subagents"),
    ("GET", "/subagents/{run_id}"),
    ("POST", "/subagents/run"),
    ("GET", "/hooks/status"),
    ("POST", "/hooks/reload"),
    ("POST", "/teams/run"),
    ("POST", "/teams/spawn"),
    ("GET", "/teams"),
    ("GET", "/teams/{team_id}"),
    ("POST", "/orchestrator/spawn"),
    ("POST", "/orchestrator/run"),
    ("GET", "/orchestrator"),
    ("GET", "/orchestrator/{run_id}"),
    ("GET", "/improve/status"),
    ("POST", "/improve/scan"),
    ("GET", "/improve/pending"),
    ("POST", "/improve/review"),
    ("POST", "/improve/export"),
    ("GET", "/bgjobs"),
    ("GET", "/bgjobs/dequeue"),
    ("GET", "/bgjobs/{job_id}"),
    ("DELETE", "/bgjobs/{job_id}"),
    ("POST", "/bgjobs/{job_id}/finish"),
    ("GET", "/lora/status"),
    ("POST", "/lora/deploy"),
    ("POST", "/cursor/tasks"),
    ("POST", "/cursor/tasks/run"),
}


_SKIP_PATHS = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}


def _collect_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path or not methods or path in _SKIP_PATHS:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.add((method, path))
    return out


def test_all_routes_present():
    actual = _collect_routes()
    missing = EXPECTED_ROUTES - actual
    assert not missing, f"missing routes: {sorted(missing)}"


def test_route_count():
    actual = _collect_routes()
    assert len(actual) == len(EXPECTED_ROUTES), (
        f"expected {len(EXPECTED_ROUTES)} routes, got {len(actual)}; "
        f"extra={sorted(actual - EXPECTED_ROUTES)}"
    )
