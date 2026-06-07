"""P8 Platform Subagents tab."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_list, register_tools_spawn


class SubagentBody(BaseModel):
    task: str
    budget_iters: int = 3
    user_id: int | None = None


async def _spawn_subagent(tools: Any, auth: PlatformAuth, body: SubagentBody) -> dict[str, Any]:
    uid = resolve_uid(auth, body.user_id)
    return await tools.spawn_subagent(uid, body.task, body.budget_iters)


def register(router: APIRouter) -> None:
    register_tools_list(router, "/platform/api/subagents", "list_subagents", wrap_key="runs")
    register_tools_spawn(
        router,
        "/platform/api/subagents",
        SubagentBody,
        tools_attr="spawn_subagent",
        call=_spawn_subagent,
    )
