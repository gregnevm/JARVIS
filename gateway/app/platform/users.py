"""P0.7 Users — доступ (approve/deny/revoke) + скидання rate-limit.

Reuse AccessStore і нотифікації з admin_panel — Platform лише інший фронт до тієї
самої логіки доступу. .env-whitelist (ALLOWED_USER_IDS) керується файлом, не тут.
"""
from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..access_store import AccessStore
from ..admin_panel import _primary_admin_id, _user_json
from ..auth import allowed_ids_snapshot
from ..bot.admin import execute_action
from ..config import settings
from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.users")


class UserIdBody(BaseModel):
    user_id: int = Field(..., gt=0)


def register(router: APIRouter) -> None:
    @router.get("/platform/api/users")
    async def users_list(
        request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        store: AccessStore = request.app.state.access_store
        return {
            "pending": [_user_json(r) for r in store.list_pending()],
            "approved": [_user_json(r) for r in store.list_approved()],
            "env_whitelist": sorted(settings.allowed_ids),
            "dynamic_whitelist": sorted(allowed_ids_snapshot()),
            "admin_ids": sorted(settings.admin_ids),
        }

    @router.post("/platform/api/users/approve")
    async def users_approve(
        body: UserIdBody, request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        store: AccessStore = request.app.state.access_store
        uid = body.user_id
        if uid in settings.allowed_ids:
            return {"ok": False, "message": "already in .env whitelist"}
        ok, msg, rec = await store.approve(uid, by_admin=_primary_admin_id())
        if not ok:
            return {"ok": False, "message": msg}
        if rec is not None:
            try:
                await request.app.state.tg.send_message(
                    uid,
                    "✅ <b>Доступ відкрито!</b>\n\nНапиши /start — можна користуватись JARVIS.",
                    parse_mode="HTML",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("approve notify %s failed: %s", uid, exc)
        return {"ok": True, "user": _user_json(rec) if rec else {"user_id": uid}}

    @router.post("/platform/api/users/deny")
    async def users_deny(
        body: UserIdBody, request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        store: AccessStore = request.app.state.access_store
        ok, msg = await store.deny(body.user_id)
        return {"ok": ok, "message": msg}

    @router.post("/platform/api/users/revoke")
    async def users_revoke(
        body: UserIdBody, request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        uid = body.user_id
        if uid in settings.allowed_ids:
            return {"ok": False, "message": "remove from ALLOWED_USER_IDS in .env"}
        store: AccessStore = request.app.state.access_store
        ok, msg = await store.revoke(uid)
        if ok:
            try:
                await request.app.state.tg.send_message(uid, "Доступ до JARVIS закрито.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("revoke notify %s failed: %s", uid, exc)
        return {"ok": ok, "message": msg}

    @router.post("/platform/api/users/ratelimit/reset")
    async def users_ratelimit_reset(
        body: UserIdBody, request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        redis: aioredis.Redis = request.app.state.redis
        text = await execute_action(f"rl:{body.user_id}", request.app.state.svc, redis)
        return {"ok": "✅" in text, "message": text}
