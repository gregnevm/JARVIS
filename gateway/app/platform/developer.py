"""Developer console (AP-3) — keys + usage у `/platform` для авторизованого адміна.

Data-шар консолі: перевикористовує `ApiKeyStore` (AP-1) та `UsageStore` (AP-2.4),
але гейт — сесія Platform-консолі (`require_platform_auth`), а не root-bearer. Тобто
адмін керує ключами з UI, не вставляючи root-ключ. Per-org tenant — поверх пізніше.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .._helpers import AGENT_MODES_AUTO, require_mode
from ..saas.api_keys import ApiKeyStore
from ..saas.request_log import RequestLogStore
from ..saas.usage import UsageStore
from .auth import PlatformAuth, require_platform_auth


class KeyCreateBody(BaseModel):
    name: str = ""
    scopes: list[str] | None = None


class PlaygroundBody(BaseModel):
    input: str
    mode: str = "auto"


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

    @router.get("/platform/api/developer/logs")
    async def logs(
        request: Request, limit: int = 50, _: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        """AP-3.4: останні `/v1`-запити (status/latency/endpoint/key)."""
        return {"data": await RequestLogStore(request.app.state.redis).recent(limit=limit)}

    @router.post("/platform/api/developer/playground")
    async def playground(
        request: Request,
        body: PlaygroundBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        """AP-3.3: пробний `/v1`-виклик із консолі (admin-сесія, без вставляння ключа)."""
        text = (body.input or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="input required")
        mode = require_mode(body.mode or "auto", AGENT_MODES_AUTO)  # fail-fast (P2)
        result = await request.app.state.tools.process(
            {"user_id": auth.user_id, "text": text, "mode": mode}
        )
        return {"output": result}
