"""Рутини у штабі /platform (SY-9.4): список активних + «вимкнути» одним кліком.

Тонкий проксі до tools `/routines/*` — та сама механіка, що client-API (S4:
disable = явний клік користувача в штабі).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .auth import PlatformAuth, require_platform_auth


class _DisableBody(BaseModel):
    job: str


async def _tools(method: str, path: str, **kw: Any) -> dict[str, Any]:
    try:
        return await call_dict(
            settings.tools_url, method, path, timeout=30.0, service="tools", **kw
        )
    except ServiceError:
        return {"error": "tools unreachable"}


def register(router: APIRouter) -> None:
    @router.get("/platform/api/routines")
    async def platform_routines(
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        return await _tools("GET", "/routines/list")

    @router.post("/platform/api/routines/disable")
    async def platform_routines_disable(
        body: _DisableBody, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await _tools(
            "POST", "/routines/disable", json={"user_id": auth.user_id, "job": body.job}
        )
