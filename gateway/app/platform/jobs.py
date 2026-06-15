"""P2 Platform Jobs tab — background agent tasks."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from jarvis_core.bg_jobs import platform_create_method
from pydantic import BaseModel

from .._helpers import require_text
from .auth import PlatformAuth, require_platform_auth, resolve_uid
from .proxy import register_tools_get_by_id, register_tools_list


class JobCreateBody(BaseModel):
    text: str
    mode: str = "auto"
    job_type: str = "agent_turn"
    max_hops: int = 3
    user_id: int | None = None


def register(router: APIRouter) -> None:
    register_tools_list(
        router,
        "/platform/api/jobs",
        "list_bg_jobs",
        wrap_key="jobs",
    )

    @router.post("/platform/api/jobs")
    async def jobs_create(
        request: Request,
        body: JobCreateBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        text = require_text(body.text)
        uid = resolve_uid(auth, body.user_id)
        jt = (body.job_type or "agent_turn").strip()
        tools = request.app.state.tools
        method_name = platform_create_method(jt)
        create_fn = getattr(tools, method_name)
        if method_name == "create_research_job":
            job = await create_fn(uid, text, body.max_hops)
        elif method_name == "create_cursor_job":
            job = await create_fn(uid, text)
        else:
            job = await create_fn(uid, text, body.mode)
        if job.get("error"):
            raise HTTPException(status_code=502, detail=str(job["error"]))
        return job

    register_tools_get_by_id(
        router,
        "/platform/api/jobs/{job_id}",
        "get_bg_job",
        id_name="job_id",
        not_found="job not found",
        owner_scoped=True,
    )

    @router.delete("/platform/api/jobs/{job_id}")
    async def jobs_cancel(
        job_id: str,
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int | None = None,
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, user_id)
        ok = await request.app.state.tools.cancel_bg_job(job_id, uid)
        if not ok:
            raise HTTPException(status_code=404, detail="job not found or not cancellable")
        return {"ok": True}
