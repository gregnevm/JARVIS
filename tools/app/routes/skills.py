"""Skills endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import SkillActiveBody
from ._helpers import require_found


def register(router: APIRouter) -> None:
    @router.get("/skills")
    async def skills_list_ep() -> dict[str, Any]:
        from .. import skills

        return {"skills": skills.list_skills()}

    @router.get("/skills/{skill_id}")
    async def skills_get_ep(skill_id: str) -> dict[str, Any]:
        from .. import skills

        return require_found(skills.get_skill(skill_id), detail="skill not found")

    @router.post("/skills/active")
    async def skills_active_ep(body: SkillActiveBody) -> dict[str, Any]:
        from .. import skills

        await skills.set_active_skill(body.user_id, body.skill_id)
        active = await skills.active_skill_id(body.user_id)
        return {"user_id": body.user_id, "skill_id": active}

    @router.get("/skills/active/{user_id}")
    async def skills_active_get_ep(user_id: int) -> dict[str, Any]:
        from .. import skills

        sid = await skills.active_skill_id(user_id)
        if not sid:
            return {"user_id": user_id, "skill_id": None}
        rec = skills.get_skill(sid)
        return {"user_id": user_id, "skill_id": sid, "skill": rec}
