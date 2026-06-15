"""Self-improve loop endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import ImproveReviewBody


def register(router: APIRouter) -> None:
    @router.get("/improve/status")
    async def improve_status_ep(user_id: int | None = None) -> dict[str, Any]:
        from .. import self_improve

        return self_improve.improve_status(user_id)

    @router.post("/improve/scan")
    async def improve_scan_ep(user_id: int | None = None, limit: int = 0) -> dict[str, Any]:
        from .. import self_improve

        lim = limit or settings.self_improve_scan_limit
        return await self_improve.scan_sessions(user_id=user_id, limit=lim)

    @router.get("/improve/pending")
    async def improve_pending_ep(limit: int = 50) -> dict[str, Any]:
        from .. import self_improve

        return {"pending": self_improve.list_pending(limit=limit)}

    @router.post("/improve/review")
    async def improve_review_ep(body: ImproveReviewBody) -> dict[str, Any]:
        from .. import self_improve

        if not body.item_ids:
            raise HTTPException(status_code=400, detail="item_ids required")
        try:
            return self_improve.review_items(body.item_ids, body.action, reviewer=body.reviewer)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/improve/export")
    async def improve_export_ep(user_id: int | None = None) -> dict[str, Any]:
        from .. import self_improve

        return self_improve.export_approved_to_sharegpt(user_id=user_id)
