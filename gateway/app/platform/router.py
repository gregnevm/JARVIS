"""Platform router — `/platform` SPA shell + реєстрація API-модулів (P0).

Композиція замість моноліту (принцип P3): кожна можливість — окремий модуль із
`register(router)`. Нові розділи додаються сюди одним рядком.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from . import apk, logs, memory, models, overview, projects, settings_api, users, workbench
from . import autopilot as platform_autopilot
from . import coding as platform_coding
from . import connectors as platform_connectors
from . import developer as platform_developer
from . import hooks as platform_hooks
from . import improve as platform_improve
from . import jobs as platform_jobs
from . import mcp as platform_mcp
from . import orchestrator as platform_orchestrator
from . import plans as platform_plans
from . import research as platform_research
from . import skills as platform_skills
from . import subagents as platform_subagents
from . import team as platform_team
from . import teams as platform_teams
from .auth import PlatformAuth, require_platform_auth, resolve_context

router = APIRouter()

_INDEX = Path(__file__).parent.parent / "static" / "platform.html"
_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@router.get("/platform", response_class=HTMLResponse)
async def platform_index() -> HTMLResponse:
    try:
        body = _INDEX.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HTMLResponse("<h1>Platform UI not built</h1>", status_code=404)
    return HTMLResponse(body, headers=_NO_CACHE)


@router.get("/platform/api/whoami")
async def platform_whoami(auth: PlatformAuth = Depends(require_platform_auth)) -> dict[str, object]:
    # tenant-ґрунт PR#1: розширено org/role/plan/legacy_uid із RequestContext.
    # `user_id` лишається int (Telegram id) для backward compat з наявним platform.html.
    ctx = resolve_context(auth)
    return {
        "via": ctx.via,
        "user_id": auth.user_id,
        "org_id": ctx.org_id,
        "role": ctx.role,
        "plan": ctx.plan,
        "legacy_uid": ctx.legacy_uid,
    }


for _mod in (
    overview,
    workbench,
    memory,
    projects,
    logs,
    settings_api,
    users,
    models,
    platform_jobs,
    platform_plans,
    platform_research,
    platform_mcp,
    platform_connectors,
    platform_skills,
    platform_subagents,
    platform_hooks,
    platform_teams,
    platform_orchestrator,
    platform_improve,
    platform_autopilot,
    platform_developer,
    platform_coding,
    platform_team,
    apk,
):
    _mod.register(router)
