"""P3 Platform Planning — proxy до tools /agent/plan*."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .._helpers import require_found, require_text
from .auth import PlatformAuth, require_platform_auth, resolve_uid
from .proxy import register_tools_get_by_id, register_tools_list


class PlanCreateBody(BaseModel):
    text: str
    user_id: int | None = None


class PlanUserBody(BaseModel):
    user_id: int | None = None


def register(router: APIRouter) -> None:
    register_tools_list(
        router,
        "/platform/api/plans",
        "list_plans",
        wrap_key="plans",
    )

    @router.post("/platform/api/plans")
    async def plans_create(
        request: Request,
        body: PlanCreateBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        text = require_text(body.text)
        uid = resolve_uid(auth, body.user_id)
        plan = await request.app.state.tools.create_plan(uid, text)
        if plan.get("error"):
            raise HTTPException(status_code=502, detail=str(plan["error"]))
        return plan

    register_tools_get_by_id(
        router,
        "/platform/api/plans/{plan_id}",
        "get_plan",
        id_name="plan_id",
        not_found="plan not found",
    )

    @router.post("/platform/api/plans/{plan_id}/approve")
    async def plans_approve(
        plan_id: str,
        request: Request,
        body: PlanUserBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, body.user_id)
        return require_found(
            await request.app.state.tools.approve_plan(plan_id, uid), detail="plan not found"
        )

    @router.post("/platform/api/plans/{plan_id}/deny")
    async def plans_deny(
        plan_id: str,
        request: Request,
        body: PlanUserBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, body.user_id)
        return require_found(
            await request.app.state.tools.deny_plan(plan_id, uid), detail="plan not found"
        )

    @router.post("/platform/api/plans/{plan_id}/execute")
    async def plans_execute(
        plan_id: str,
        request: Request,
        body: PlanUserBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, body.user_id)
        result = await request.app.state.tools.execute_plan(plan_id, uid)
        if result.get("error") and result.get("plan") is None:
            raise HTTPException(status_code=400, detail=str(result["error"]))
        return result
