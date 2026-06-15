"""P4 Platform Research tab — deep research jobs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_spawn


class ResearchCreateBody(BaseModel):
    query: str
    max_hops: int = 3
    user_id: int | None = None


async def _create_research(tools: Any, auth: PlatformAuth, body: ResearchCreateBody) -> dict[str, Any]:
    uid = resolve_uid(auth, body.user_id)
    return await tools.create_research_job(uid, body.query, body.max_hops)


def register(router: APIRouter) -> None:
    register_tools_spawn(
        router,
        "/platform/api/research",
        ResearchCreateBody,
        tools_attr="create_research_job",
        call=_create_research,
        required_field="query",
    )
