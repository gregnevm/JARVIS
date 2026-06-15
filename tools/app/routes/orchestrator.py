"""Orchestrator + Critic endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..schemas import OrchestratorRunBody, OrchestratorSpawnBody
from ._helpers import require_found, require_text


def register(router: APIRouter) -> None:
    @router.post("/orchestrator/spawn")
    async def orchestrator_spawn_ep(body: OrchestratorSpawnBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, orchestrator

        if not settings.orchestrator_enabled:
            raise HTTPException(status_code=503, detail="orchestrator disabled")
        task = require_text(body.task)
        rec = await orchestrator.create_run(
            body.user_id,
            task,
            worker_budget=body.worker_budget,
            max_revisions=body.max_revisions,
        )
        if body.async_mode:
            job = await bg_jobs.create_orchestrator_job(
                body.user_id,
                task,
                run_id=rec["id"],
                worker_budget=body.worker_budget,
                max_revisions=body.max_revisions,
            )
            rec["job_id"] = job.get("id")
        else:
            result = await orchestrator.run_orchestrator_pipeline(
                request.app.state.chat_backend,
                request.app.state.agent,
                body.user_id,
                rec["id"],
            )
            rec = await orchestrator.get_run(rec["id"]) or rec
            rec["sync_result"] = result
        return rec

    @router.post("/orchestrator/run")
    async def orchestrator_run_ep(body: OrchestratorRunBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, orchestrator

        async def _prog(pct: int, msg: str) -> None:
            if body.job_id:
                await bg_jobs.update_progress(body.job_id, pct, msg)

        result = await orchestrator.run_orchestrator_pipeline(
            request.app.state.chat_backend,
            request.app.state.agent,
            body.user_id,
            body.run_id,
            progress_cb=_prog if body.job_id else None,
        )
        if result.get("error"):
            if body.job_id:
                await bg_jobs.finish_job(body.job_id, error=str(result["error"])[:500], status="failed")
            raise HTTPException(status_code=502, detail=str(result["error"]))
        final = str(result.get("result") or "")
        if body.job_id:
            await bg_jobs.finish_job(body.job_id, result=final, status="done")
        return result

    @router.get("/orchestrator")
    async def orchestrator_list_ep(user_id: int, limit: int = 20) -> dict[str, Any]:
        from .. import orchestrator

        return {"runs": await orchestrator.list_runs(user_id, limit), "user_id": user_id}

    @router.get("/orchestrator/{run_id}")
    async def orchestrator_get_ep(run_id: str, user_id: int) -> dict[str, Any]:
        from .. import orchestrator

        return require_found(
            await orchestrator.get_run(run_id, user_id), detail="orchestrator run not found"
        )
