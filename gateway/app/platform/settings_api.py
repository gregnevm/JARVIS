"""P0.6 Settings — runtime-прапори (streaming/voice/mode) + read-only .env знімок.

Прапори через Redis (як `/app/flags`), режим агента через tools `/mode`. Зміни .env
лишаються поза UI (recreate контейнерів) — показуємо лише знімок.
"""
from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .._helpers import AGENT_MODES, require_mode
from ..admin_panel import _settings_snapshot
from ..runtime_flags import get_flags, set_flag
from ..services import ServicesClient
from .auth import PlatformAuth, require_platform_auth

_FLAGS = {"streaming", "voice_reply"}


class FlagBody(BaseModel):
    name: str
    enabled: bool


class ModeBody(BaseModel):
    mode: str


def register(router: APIRouter) -> None:
    @router.get("/platform/api/settings")
    async def settings_get(
        request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        svc: ServicesClient = request.app.state.svc
        redis: aioredis.Redis = request.app.state.redis
        core = await svc.dashboard()
        flags = await get_flags(redis)
        return {
            "flags": flags,
            "env": _settings_snapshot(core),
            "agent_mode": core.get("agent_mode"),
            "agent_mode_env": core.get("agent_mode_env"),
        }

    @router.post("/platform/api/settings/flag")
    async def settings_flag(
        request: Request,
        body: FlagBody,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        if body.name not in _FLAGS:
            raise HTTPException(status_code=400, detail="bad flag")
        await set_flag(request.app.state.redis, body.name, body.enabled)
        return {"ok": True, "flags": await get_flags(request.app.state.redis)}

    @router.post("/platform/api/settings/mode")
    async def settings_mode(
        request: Request,
        body: ModeBody,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        mode = require_mode(body.mode, AGENT_MODES)
        return await request.app.state.svc.set_mode(mode)

    @router.delete("/platform/api/settings/mode")
    async def settings_mode_reset(
        request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.svc.reset_mode()
