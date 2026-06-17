"""Driver — керування PC-ендпоінтом з іншого ендпоінта (аналог dispatch + computer-use
+ remote desktop) з текстовим/голосовим copilot.

Переюзає наявний computer-use (hostagent через tools) під єдиною client-API auth:
  POST /api/v1/driver/exec        — команда в computer-режимі (агент керує PC; мутуючі дії
                                     просять підтвердження через /api/v1/confirm — S4)
  POST /api/v1/driver/screenshot  — кадр екрана PC
  GET  /api/v1/driver/status      — стан computer-use / trust
Copilot (текст/голос) — наявні /api/v1/chat та /api/v1/voice. За прапором ENABLE_COMPUTER_USE.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from ..agent_payload import build_agent_payload
from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.driver")


class DriverExec(BaseModel):
    text: str


def _uid(ctx: RequestContext) -> int:
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id")


async def _tools(method: str, path: str, payload: dict[str, Any] | None = None,
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as cli:
        r = await cli.request(method, f"{settings.tools_url.rstrip('/')}{path}",
                              json=payload, params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


def register(router: APIRouter) -> None:
    @router.post("/driver/exec")
    async def driver_exec(body: DriverExec, request: Request,
                          ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        uid = _uid(ctx)
        payload = build_agent_payload(user_id=uid, chat_id=uid, text=text,
                                      source="driver", mode="computer")
        reply = await request.app.state.tools.process(payload)
        return {"reply": reply, "mode": "computer"}

    @router.post("/driver/screenshot")
    async def driver_screenshot(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _tools("POST", "/computer/screenshot", {"user_id": _uid(ctx)})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="computer-use unreachable") from exc

    @router.get("/driver/status")
    async def driver_status(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            st = await _tools("GET", "/computer/trust/status", params={"user_id": _uid(ctx)})
        except httpx.HTTPError:
            st = {"error": "computer-use unreachable"}
        return {"enabled": settings.enable_computer_use if hasattr(settings, "enable_computer_use") else None,
                "trust": st}
