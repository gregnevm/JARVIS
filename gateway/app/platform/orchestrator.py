"""Phase 7.1 Platform Orchestrator tab."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_list, register_tools_spawn


class OrchestratorBody(BaseModel):
    task: str
    worker_budget: int = 5
    user_id: int | None = None


async def _spawn_orchestrator(tools: Any, auth: PlatformAuth, body: OrchestratorBody) -> dict[str, Any]:
    uid = resolve_uid(auth, body.user_id)
    return await tools.spawn_orchestrator(uid, body.task, worker_budget=body.worker_budget)


def register(router: APIRouter) -> None:
    register_tools_list(router, "/platform/api/orchestrator", "list_orchestrator_runs", wrap_key="runs")
    register_tools_spawn(
        router,
        "/platform/api/orchestrator",
        OrchestratorBody,
        tools_attr="spawn_orchestrator",
        call=_spawn_orchestrator,
    )
