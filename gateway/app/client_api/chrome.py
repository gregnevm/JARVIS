"""Chrome use — двосторонній контроль Chromium через extension-ендпоінт.

Черга команд у Redis (org-scoped): агент/клієнт кладе команду → розширення опитує
`/poll`, виконує в браузері (DOM/навігація), повертає `/result`. І навпаки — розширення
може штовхати контекст сторінки. Доповнює headless-Playwright (`tools/browser.py`)
контролем РЕАЛЬНОГО браузера користувача через `extension/`.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID, RequestContext, redis_key

from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.chrome")

_TTL = 120  # сек життя команди/результату


class ChromeCommand(BaseModel):
    action: str               # navigate|click|fill|read|eval|screenshot…
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    script: str | None = None


class ChromeResult(BaseModel):
    id: str
    ok: bool = True
    result: Any = None


def _ctx_keys(ctx: RequestContext) -> tuple[str, str]:
    org = ctx.org_id or DEFAULT_ORG_ID
    uid = str(ctx.legacy_uid if ctx.legacy_uid is not None else ctx.user_id)
    return redis_key(org, "chrome", "queue", uid), redis_key(org, "chrome", "res", uid)


def register(router: APIRouter) -> None:
    @router.post("/chrome/command")
    async def chrome_command(body: ChromeCommand, request: Request,
                             ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Покласти команду для браузера. Повертає id для опитування результату."""
        redis: aioredis.Redis = request.app.state.redis
        qkey, _ = _ctx_keys(ctx)
        cmd_id = secrets.token_urlsafe(9)
        cmd = {"id": cmd_id, **body.model_dump(exclude_none=True)}
        await redis.lpush(qkey, json.dumps(cmd))
        await redis.expire(qkey, _TTL)
        return {"id": cmd_id, "queued": True}

    @router.get("/chrome/poll")
    async def chrome_poll(request: Request,
                          ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Розширення опитує наступну команду (FIFO). {} якщо черга порожня."""
        redis: aioredis.Redis = request.app.state.redis
        qkey, _ = _ctx_keys(ctx)
        raw = await redis.rpop(qkey)
        if not raw or not isinstance(raw, (str, bytes, bytearray)):
            return {}
        try:
            return dict(json.loads(raw))
        except (ValueError, TypeError):
            return {}

    @router.post("/chrome/result")
    async def chrome_result(body: ChromeResult, request: Request,
                            ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Розширення повертає результат виконання команди."""
        redis: aioredis.Redis = request.app.state.redis
        _, rkey = _ctx_keys(ctx)
        await redis.setex(f"{rkey}:{body.id}", _TTL,
                          json.dumps({"ok": body.ok, "result": body.result}))
        return {"stored": True}

    @router.get("/chrome/result/{cmd_id}")
    async def chrome_get_result(cmd_id: str, request: Request,
                                ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Клієнт/агент читає результат команди (pending, якщо ще не виконано)."""
        redis: aioredis.Redis = request.app.state.redis
        _, rkey = _ctx_keys(ctx)
        raw = await redis.get(f"{rkey}:{cmd_id}")
        if not raw:
            return {"status": "pending"}
        try:
            return {"status": "done", **json.loads(raw)}
        except (ValueError, TypeError):
            raise HTTPException(status_code=500, detail="bad result payload")
