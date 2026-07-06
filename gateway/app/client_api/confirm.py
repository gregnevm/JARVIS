"""BE5 — computer-confirm міст для mobile/SPA (поза Telegram, CL-3.5 / CC5).

Тонкий проксі до tools `/computer/{pending,confirm,cancel}` під єдиною client-API auth.
Org-scoped (user_id з RequestContext). Дозволяє апрувити дії агента з телефона нативно.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .deps import context_uid as _uid, resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.confirm")


class ApproveBody(BaseModel):
    code: str


async def _tools_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    return await call_dict(
        settings.tools_url, "GET", path, params=params, timeout=15.0, service="tools"
    )


async def _tools_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_dict(
        settings.tools_url, "POST", path, json=payload, timeout=60.0, service="tools"
    )


def register(router: APIRouter) -> None:
    @router.get("/confirm/pending")
    async def confirm_pending(
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        try:
            return await _tools_get("/computer/pending", {"user_id": _uid(ctx)})
        except ServiceError as exc:
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
        except ServiceError as exc:
            logger.warning("confirm approve failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc

    @router.post("/confirm/cancel")
    async def confirm_cancel(
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        try:
            return await _tools_post("/computer/cancel", {"user_id": _uid(ctx)})
        except ServiceError as exc:
            logger.warning("confirm cancel failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc
