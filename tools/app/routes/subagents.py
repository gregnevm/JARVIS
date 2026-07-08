"""Subagents endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..schemas import SubagentRunBody, SubagentSpawnBody
from ._helpers import clamp_budget, require_found, require_text


def register(router: APIRouter) -> None:
    @router.post("/subagents/spawn")
    async def subagents_spawn_ep(body: SubagentSpawnBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, subagents

        task = require_text(body.task)
        budget = clamp_budget(body.budget_iters)
        rec = await subagents.create_spawn(body.user_id, task, budget_iters=budget, mode=body.mode)
        if body.async_mode:
            job = await bg_jobs.create_subagent_job(
                body.user_id,
                task,
                budget_iters=budget,
                run_id=rec["id"],
                mode=body.mode,
            )
            rec["job_id"] = job.get("id")
        else:
            result = await request.app.state.agent.run(
                body.user_id,
                task,
                mode=body.mode,
                max_iters_override=budget,
            )
            await subagents.finish_run(
                rec["id"],
                result=str(result.get("text") or ""),
                iters_used=int(result.get("iters") or 0),
                status="done",
            )
            rec = await subagents.get_run(rec["id"]) or rec
        return rec

    @router.get("/subagents")
    async def subagents_list_ep(user_id: int, limit: int = 20) -> dict[str, Any]:
        from .. import subagents

        return {"runs": await subagents.list_runs(user_id, limit), "user_id": user_id}

    @router.get("/subagents/{run_id}")
    async def subagents_get_ep(run_id: str, user_id: int) -> dict[str, Any]:
        from .. import subagents

        return require_found(
            await subagents.get_run(run_id, user_id), detail="subagent run not found"
        )

    @router.post("/subagents/run")
    async def subagents_run_ep(body: SubagentRunBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, subagents

        task = require_text(body.task)
        # Anti-IDOR (AGENTS §5, mirrors orchestrator.py:167): the body forwards a
        # caller-supplied run_id, and mark_running/finish_run below rewrite the
        # record (status/result/error/iters). Without the owner filter user A could
        # overwrite user B's subagent run + leak the slot. get_run returns None on
        # owner mismatch (redis_store owner_user_id gate) → fail closed to 404.
        if await subagents.get_run(body.run_id, body.user_id) is None:
            raise HTTPException(status_code=404, detail="subagent run not found")
        await subagents.mark_running(body.run_id)
        try:
            result = await request.app.state.agent.run(
                body.user_id,
                task,
                mode=body.mode,
                max_iters_override=body.budget_iters,
            )
            text = str(result.get("text") or "")
            await subagents.finish_run(
                body.run_id,
                result=text,
                iters_used=int(result.get("iters") or 0),
                status="done",
            )
            if body.job_id:
                await bg_jobs.finish_job(body.job_id, result=text, status="done")
            return {"result": text, "iters": result.get("iters", 0)}
        except Exception as exc:  # noqa: BLE001
            await subagents.finish_run(body.run_id, error=str(exc), status="failed")
            if body.job_id:
                await bg_jobs.finish_job(body.job_id, error=str(exc)[:500], status="failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
