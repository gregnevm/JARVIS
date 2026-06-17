"""Context-maintenance jobs — ручний тригер (ADR-008: maintenance із нагляду, не auto-cron).

POST /context/jobs/{name} — name ∈ {context_summarize, context_daily, context_retention}.
Виконавець із реальним memory+Ollama — у `context_jobs.run_context_job`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..context_jobs import CONTEXT_JOB_NAMES, run_context_job


def register(router: APIRouter) -> None:
    @router.post("/context/jobs/{name}")
    async def run_ctx_job(name: str, request: Request, user_id: int) -> dict[str, Any]:
        if name not in CONTEXT_JOB_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown context job: {name}")
        now = datetime.now(timezone.utc)
        return await run_context_job(
            name,
            request.app.state.memory,
            request.app.state.chat_backend,
            user_id,
            day=now.date().isoformat(),
            now=now,
        )
