"""BE5 — computer-confirm міст для mobile/SPA (поза Telegram, CL-3.5 / CC5).

Тонкий проксі до tools `/computer/{pending,confirm,cancel}` під єдиною client-API auth.
Org-scoped (user_id з RequestContext). Дозволяє апрувити дії агента з телефона нативно.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.confirm")


class ApproveBody(BaseModel):
    code: str


def _uid(ctx: RequestContext) -> int:
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id")


async def _tools_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.get(f"{settings.tools_url.rstrip('/')}{path}", params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


async def _tools_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as cli:
        r = await cli.post(f"{settings.tools_url.rstrip('/')}{path}", json=payload)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


def register(router: APIRouter) -> None:
    @router.get("/confirm/pending")
    async def confirm_pending(
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        try:
            return await _tools_get("/computer/pending", {"user_id": _uid(ctx)})
        except httpx.HTTPError as exc:
            logger.warning("confirm pending failed: %s", type(exc).__name__)
            return {"pending": False, "error": "tools_unreachable"}

    @router.post("/confirm/approve")
    async def confirm_approve(
        body: ApproveBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        if not body.code.strip():
            raise HTTPException(status_code=400, detail="code required")
        try:
            return await _tools_post(
                "/computer/confirm", {"user_id": _uid(ctx), "code": body.code.strip()}
            )
        except httpx.HTTPError as exc:
            logger.warning("confirm approve failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc

    @router.post("/confirm/cancel")
    async def confirm_cancel(
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        try:
            return await _tools_post("/computer/cancel", {"user_id": _uid(ctx)})
        except httpx.HTTPError as exc:
            logger.warning("confirm cancel failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc
