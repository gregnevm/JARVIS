"""Deep research endpoints."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from ..schemas import ResearchRequest, ResearchRunRequest
from ._helpers import require_text


def register(router: APIRouter) -> None:
    @router.post("/research")
    async def research_enqueue(req: ResearchRequest) -> dict[str, Any]:
        from .. import bg_jobs

        query = require_text(req.query, field="query")
        if req.async_mode:
            return await bg_jobs.create_research_job(req.user_id, query, req.max_hops)
        from .. import research

        return await research.deep_research(query, max_hops=req.max_hops)

    @router.post("/research/run")
    async def research_run(req: ResearchRunRequest, request: Request) -> dict[str, Any]:
        from .. import bg_jobs, research

        query = require_text(req.query, field="query")

        async def _prog(pct: int, msg: str) -> None:
            await bg_jobs.update_progress(req.job_id, pct, msg, user_id=req.user_id)

        result = await research.deep_research_with_llm(
            query,
            request.app.state.chat_backend,
            max_hops=req.max_hops,
            progress=_prog,
        )
        report = str(result.get("report") or "")
        payload = json.dumps(result, ensure_ascii=False)
        await bg_jobs.finish_job(req.job_id, result=payload, status="done", user_id=req.user_id)
        return {"report": report, "sources": result.get("sources") or []}
