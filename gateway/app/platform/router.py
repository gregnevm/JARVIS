"""Platform router — `/platform` SPA shell + реєстрація API-модулів (P0).

Композиція замість моноліту (принцип P3): кожна можливість — окремий модуль із
`register(router)`. Нові розділи додаються сюди одним рядком.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from . import logs, memory, models, overview, projects, settings_api, users, workbench
from .auth import PlatformAuth, require_platform_auth

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
    return {"via": auth.via, "user_id": auth.user_id}


for _mod in (overview, workbench, memory, projects, logs, settings_api, users, models):
    _mod.register(router)
