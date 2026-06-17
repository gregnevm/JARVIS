"""API-key management endpoints (AP-1.3): create / list / revoke.

Gated to the **root** key (`OPENAI_API_KEY`) — minting/revoking credentials is an
admin action; minted sub-keys cannot manage other keys. Self-hosted: the owner's
root key acts as the org admin. Keys are show-once (full key only in create resp).
"""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from .api_keys import ApiKeyStore

router = APIRouter(prefix="/saas/api", tags=["saas"])


class KeyCreateBody(BaseModel):
    name: str = ""
    scopes: list[str] | None = None


def _require_root(request: Request) -> None:
    """Лише глобальний root-ключ може керувати ключами."""
    if not settings.enable_openai_api:
        raise HTTPException(status_code=404, detail="API platform disabled")
    root_key = (settings.openai_api_key or "").strip()
    if not root_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY (root) not configured")
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not hmac.compare_digest(auth[7:].strip(), root_key):
        raise HTTPException(status_code=403, detail="root key required to manage api keys")


def _store(request: Request) -> ApiKeyStore:
    return ApiKeyStore(request.app.state.redis)


def register(app: Any) -> None:
    @router.post("/keys")
    async def create_key(
        request: Request, body: KeyCreateBody, _: None = Depends(_require_root)
    ) -> dict[str, Any]:
        return await _store(request).create(name=body.name, scopes=body.scopes)

    @router.get("/keys")
    async def list_keys(request: Request, _: None = Depends(_require_root)) -> dict[str, Any]:
        return {"data": await _store(request).list(), "object": "list"}

    @router.delete("/keys/{key_id}")
    async def revoke_key(
        request: Request, key_id: str, _: None = Depends(_require_root)
    ) -> dict[str, Any]:
        ok = await _store(request).revoke(key_id)
        if not ok:
            raise HTTPException(status_code=404, detail="key not found")
        return {"id": key_id, "revoked": True}

    app.include_router(router)
