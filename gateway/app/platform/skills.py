"""P7 Platform Skills tab."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_get, register_tools_get_by_id, register_tools_post_call


class SkillActiveBody(BaseModel):
    skill_id: str | None = None
    user_id: int | None = None


async def _set_active_skill(tools: Any, auth: PlatformAuth, body: SkillActiveBody) -> dict[str, Any]:
    uid = resolve_uid(auth, body.user_id)
    return await tools.set_active_skill(uid, body.skill_id)


def register(router: APIRouter) -> None:
    register_tools_get(router, "/platform/api/skills", "list_skills", wrap_key="skills")
    register_tools_get_by_id(
        router,
        "/platform/api/skills/{skill_id}",
        "get_skill",
        id_name="skill_id",
        not_found="skill not found",
    )
    register_tools_post_call(
        router,
        "/platform/api/skills/active",
        SkillActiveBody,
        tools_attr="set_active_skill",
        call=_set_active_skill,
    )
