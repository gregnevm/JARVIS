"""Agent teams endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..schemas import TeamRunBody, TeamSpawnBody
from ._helpers import clamp_budget, require_found, require_text


def register(router: APIRouter) -> None:
    @router.post("/teams/run")
    async def teams_run_ep(body: TeamRunBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, teams

        async def _prog(pct: int, msg: str) -> None:
            if body.job_id:
                await bg_jobs.update_progress(body.job_id, pct, msg, user_id=body.user_id)

        result = await teams.run_team_pipeline(
            request.app.state.agent,
            body.user_id,
            body.team_id,
            progress_cb=_prog if body.job_id else None,
        )
        if result.get("error"):
            if body.job_id:
                await bg_jobs.finish_job(
                    body.job_id, error=str(result["error"])[:500], status="failed", user_id=body.user_id
                )
            raise HTTPException(status_code=502, detail=str(result["error"]))
        final = str(result.get("result") or "")
        if body.job_id:
            await bg_jobs.finish_job(body.job_id, result=final, status="done", user_id=body.user_id)
        return result

    @router.post("/teams/spawn")
    async def teams_spawn_ep(body: TeamSpawnBody, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, teams

        task = require_text(body.task)
        budget = clamp_budget(body.budget_per_role)
        # CA-5.2: kind="coding" і без явних ролей → Coder→Reviewer→Tester.
        roles = body.roles
        if not roles and body.kind.strip().lower() == "coding":
            roles = list(teams.CODING_ROLES)
        rec = await teams.create_team(
            body.user_id,
            task,
            roles=roles,
            budget_per_role=budget,
        )
        if body.async_mode:
            job = await bg_jobs.create_team_job(
                body.user_id,
                task,
                team_id=rec["id"],
                budget_per_role=budget,
                roles=roles,
            )
            rec["job_id"] = job.get("id")
        else:
            result = await teams.run_team_pipeline(request.app.state.agent, body.user_id, rec["id"])
            rec = await teams.get_team(rec["id"]) or rec
            rec["sync_result"] = result
        return rec

    @router.get("/teams")
    async def teams_list_ep(user_id: int, limit: int = 20) -> dict[str, Any]:
        from .. import teams

        return {"teams": await teams.list_teams(user_id, limit), "user_id": user_id}

    @router.get("/teams/{team_id}")
    async def teams_get_ep(team_id: str, user_id: int) -> dict[str, Any]:
        from .. import teams

        return require_found(await teams.get_team(team_id, user_id), detail="team not found")
