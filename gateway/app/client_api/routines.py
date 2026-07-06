"""Client-API: рутини (SY-9) — пропозиція стає регулярною в ≤2 кліки.

Тонкий проксі до tools `/routines/*` (де живе матеріалізація через host-agent).
S4: create/disable — явні user-initiated виклики (апрув = сам виклик); стан і
запуски видно ретривом (`kind:routine|routine_run`). Прапор фактичної дії —
tools `ENABLE_ROUTINES` (проксі не має власного прапора: вимкнено → помилка звідти).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .deps import context_uid as _uid
from .deps import resolve_client_context


class RoutineCreateBody(BaseModel):
    job: str = ""
    proposal_text: str = ""
    proposal_ref: str = ""
    hour: int = -1
    minute: int = -1


class RoutineDisableBody(BaseModel):
    job: str


async def _tools(method: str, path: str, **kw: Any) -> dict[str, Any]:
    try:
        return await call_dict(
            settings.tools_url, method, path, timeout=30.0, service="tools", **kw
        )
    except ServiceError:
        return {"error": "tools unreachable"}


def register(router: APIRouter) -> None:
    @router.post("/routines")
    async def routines_create(
        body: RoutineCreateBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        return await _tools(
            "POST", "/routines/create",
            json={
                "user_id": _uid(ctx),
                "job": body.job,
                "proposal_text": body.proposal_text,
                "proposal_ref": body.proposal_ref,
                "hour": body.hour,
                "minute": body.minute,
            },
        )

    @router.post("/routines/disable")
    async def routines_disable(
        body: RoutineDisableBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        return await _tools(
            "POST", "/routines/disable", json={"user_id": _uid(ctx), "job": body.job}
        )

    @router.get("/routines")
    async def routines_list(
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        return await _tools("GET", "/routines/list")
