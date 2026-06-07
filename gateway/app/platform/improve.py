"""Phase 7.2 Platform Self-improve (human gate)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .auth import PlatformAuth, require_platform_auth


class ImproveReviewBody(BaseModel):
    item_ids: list[str]
    action: str


def register(router: APIRouter) -> None:
    @router.get("/platform/api/improve/status")
    async def improve_status(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        return await request.app.state.tools.improve_status(auth.user_id)

    @router.post("/platform/api/improve/scan")
    async def improve_scan(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        out = await request.app.state.tools.improve_scan(auth.user_id)
        if out.get("error"):
            raise HTTPException(status_code=502, detail=str(out["error"]))
        return out

    @router.get("/platform/api/improve/pending")
    async def improve_pending(
        request: Request,
        _auth: PlatformAuth = Depends(require_platform_auth),
        limit: int = 30,
    ) -> dict[str, Any]:
        pending = await request.app.state.tools.improve_pending(limit)
        return {"pending": pending}

    @router.post("/platform/api/improve/review")
    async def improve_review(
        request: Request,
        body: ImproveReviewBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        if not body.item_ids:
            raise HTTPException(status_code=400, detail="item_ids required")
        out = await request.app.state.tools.improve_review(
            body.item_ids, body.action, reviewer=str(auth.user_id)
        )
        if out.get("error"):
            raise HTTPException(status_code=502, detail=str(out["error"]))
        return out
