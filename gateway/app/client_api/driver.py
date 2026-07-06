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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.service_client import ServiceError, call_dict

from ..agent_payload import build_agent_payload
from ..config import settings
from .deps import context_uid as _uid
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.driver")


class DriverExec(BaseModel):
    text: str


async def _tools(method: str, path: str, payload: dict[str, Any] | None = None,
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await call_dict(
        settings.tools_url, method, path,
        json=payload, params=params, timeout=60.0, service="tools",
    )


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
        except ServiceError as exc:
            raise HTTPException(status_code=502, detail="computer-use unreachable") from exc

    @router.get("/driver/status")
    async def driver_status(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            st = await _tools("GET", "/computer/trust/status", params={"user_id": _uid(ctx)})
        except ServiceError:
            st = {"error": "computer-use unreachable"}
        return {"enabled": settings.enable_computer_use if hasattr(settings, "enable_computer_use") else None,
                "trust": st}
