"""P9 Platform Agent Teams tab."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_get_by_id, register_tools_list, register_tools_spawn


class TeamBody(BaseModel):
    task: str
    budget_per_role: int = 3
    user_id: int | None = None


async def _spawn_team(tools: Any, auth: PlatformAuth, body: TeamBody) -> dict[str, Any]:
    uid = resolve_uid(auth, body.user_id)
    return await tools.spawn_team(uid, body.task, body.budget_per_role)


def register(router: APIRouter) -> None:
    register_tools_list(router, "/platform/api/teams", "list_teams", wrap_key="teams")
    register_tools_spawn(
        router,
        "/platform/api/teams",
        TeamBody,
        tools_attr="spawn_team",
        call=_spawn_team,
    )
    register_tools_get_by_id(
        router,
        "/platform/api/teams/{team_id}",
        "get_team",
        id_name="team_id",
        not_found="team not found",
    )
