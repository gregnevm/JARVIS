"""Background jobs: /bgjobs*."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas import BgJobCreate, BgJobFinish
from ._helpers import require_found


def register(router: APIRouter) -> None:
    @router.post("/bgjobs")
    async def bgjobs_create(req: BgJobCreate) -> dict[str, Any]:
        from .. import bg_jobs

        try:
            jt = (req.job_type or "agent_turn").strip()
            if jt == "deep_research":
                query = (req.text or "").strip()
                return await bg_jobs.create_research_job(req.user_id, query, req.max_hops)
            if jt == "subagent":
                task = (req.text or "").strip()
                return await bg_jobs.create_subagent_job(req.user_id, task, budget_iters=req.max_hops)
            if jt == "agent_team":
                task = (req.text or "").strip()
                return await bg_jobs.create_team_job(req.user_id, task, budget_per_role=req.max_hops)
            if jt == "cursor_task":
                task = (req.text or "").strip()
                return await bg_jobs.create_typed_job(req.user_id, "cursor_task", {"task": task})
            if jt == "coding_task":
                return await bg_jobs.create_coding_job(
                    req.user_id,
                    req.exe,
                    args=req.args,
                    path=req.path,
                    task=(req.text or "").strip(),
                    max_rounds=req.max_rounds,
                )
            return await bg_jobs.create_job(req.user_id, req.text, req.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/bgjobs")
    async def bgjobs_list(user_id: int, limit: int = 20) -> dict[str, Any]:
        from .. import bg_jobs

        return {"jobs": await bg_jobs.list_jobs(user_id, limit)}

    @router.get("/bgjobs/dequeue")
    async def bgjobs_dequeue() -> dict[str, Any]:
        from .. import bg_jobs

        job = await bg_jobs.dequeue_job()
        if job is None:
            return {"job": None}
        return {"job": job}

    @router.get("/bgjobs/{job_id}")
    async def bgjobs_get(job_id: str, user_id: int) -> dict[str, Any]:
        from .. import bg_jobs

        return require_found(await bg_jobs.get_job(job_id, user_id), detail="job not found")

    @router.delete("/bgjobs/{job_id}")
    async def bgjobs_cancel(job_id: str, user_id: int) -> dict[str, Any]:
        from .. import bg_jobs

        ok = await bg_jobs.cancel_job(job_id, user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="job not found or not cancellable")
        return {"ok": True}

    @router.post("/bgjobs/{job_id}/finish")
    async def bgjobs_finish(job_id: str, body: BgJobFinish) -> dict[str, Any]:
        from .. import bg_jobs

        status = body.status if body.status in {"done", "failed"} else ("failed" if body.error else "done")
        return require_found(
            await bg_jobs.finish_job(job_id, result=body.result, error=body.error, status=status),
            detail="job not found",
        )
