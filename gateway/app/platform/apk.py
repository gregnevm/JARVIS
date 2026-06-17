"""BE4 — web-роздача APK + пейринг (Стовп C, CL-3.1/3.8; «ендпоінт apk-додаток»).

Штаб роздає власний клієнт (APK не в Play Store через дозволи — лише sideload):
  GET  /platform/apk            — стрім підписаного APK (auth-gated)
  GET  /platform/api/apk/info   — version/size/sha256/available (паспорт артефакту)
  POST /platform/api/apk/pair   — one-time pairing-токен (Redis, org-префікс, TTL) → deeplink
Обмін токена на JWT — `POST /api/v1/auth/pair` (client_api). Generic APK + рантайм-конфіг
через deeplink — без перепідпису (рішення D-2 з proposal).
"""
from __future__ import annotations

import secrets
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from jarvis_core.context import DEFAULT_ORG_ID, redis_key

from ..apk_artifact import apk_info, read_apk_bytes
from ..config import settings
from .auth import PlatformAuth, require_platform_auth, resolve_context

_PAIR_TTL = 600  # 10 хв на пейринг
_APK_MIME = "application/vnd.android.package-archive"


def _server_base() -> str:
    raw = (settings.public_app_url or settings.gateway_browser_url or "").strip()
    for suf in ("/app", "/platform"):
        if raw.endswith(suf):
            raw = raw[: -len(suf)]
    return raw.rstrip("/")


def register(router: APIRouter) -> None:
    @router.get("/platform/apk")
    async def platform_apk_download(
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> Response:
        data = read_apk_bytes()
        info = apk_info()
        if data is None or info is None:
            return JSONResponse({"error": "apk_not_available"}, status_code=503)
        return Response(
            content=data,
            media_type=_APK_MIME,
            headers={"Content-Disposition": f'attachment; filename="{info.filename}"'},
        )

    @router.get("/platform/api/apk/info")
    async def platform_apk_info(
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        info = apk_info()
        if info is None:
            return {"available": False}
        return {
            "available": True,
            "version": info.version,
            "size": info.size,
            "sha256": info.sha256,
            "filename": info.filename,
            "built_at": info.built_at,
        }

    @router.post("/platform/api/apk/pair")
    async def platform_apk_pair(
        request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        ctx = resolve_context(auth)
        redis: aioredis.Redis = request.app.state.redis
        token = secrets.token_urlsafe(24)
        uid = ctx.legacy_uid if ctx.legacy_uid is not None else auth.user_id
        key = redis_key(ctx.org_id or DEFAULT_ORG_ID, "apk", "pair", token)
        await redis.set(key, str(uid), ex=_PAIR_TTL)
        base = _server_base()
        deeplink = f"jarvis://pair?server={base}&token={token}"
        return {"deeplink": deeplink, "server": base, "token": token, "expires_in": _PAIR_TTL}
