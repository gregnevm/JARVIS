"""Developer console (AP-3) — keys + usage у `/platform` для авторизованого адміна.

Data-шар консолі: перевикористовує `ApiKeyStore` (AP-1) та `UsageStore` (AP-2.4),
але гейт — сесія Platform-консолі (`require_platform_auth`), а не root-bearer. Тобто
адмін керує ключами з UI, не вставляючи root-ключ. Per-org tenant — поверх пізніше.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..saas.api_keys import ApiKeyStore
from ..saas.usage import UsageStore
from .auth import PlatformAuth, require_platform_auth


class KeyCreateBody(BaseModel):
    name: str = ""
    scopes: list[str] | None = None


def register(router: APIRouter) -> None:
    def _keys(request: Request) -> ApiKeyStore:
        return ApiKeyStore(request.app.state.redis)

    def _usage(request: Request) -> UsageStore:
        return UsageStore(request.app.state.redis)

    @router.get("/platform/api/developer/keys")
    async def list_keys(
        request: Request, _: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return {"data": await _keys(request).list()}

    @router.post("/platform/api/developer/keys")
    async def create_key(
        request: Request,
        body: KeyCreateBody,
        _: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        # повертає повний ключ ОДИН раз (поле `key`)
        return await _keys(request).create(name=body.name, scopes=body.scopes)

    @router.delete("/platform/api/developer/keys/{key_id}")
    async def revoke_key(
        request: Request, key_id: str, _: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        if not await _keys(request).revoke(key_id):
            raise HTTPException(status_code=404, detail="key not found")
        return {"id": key_id, "revoked": True}

    @router.get("/platform/api/developer/usage")
    async def usage(
        request: Request,
        key_id: str = "root",
        days: int = 7,
        _: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        return await _usage(request).summary(key_id or "root", days=days)
