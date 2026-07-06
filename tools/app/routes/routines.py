"""Рутини (SY-9): /routines/* — матеріалізація пропозицій у Task Scheduler."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..routines import create_routine, disable_routine, list_routines, project_proposal


class RoutineCreateRequest(BaseModel):
    user_id: int
    job: str = ""            # порожньо → проєкція з proposal_text (SY-9.1)
    proposal_text: str = ""  # текст пропозиції (для мапи і підказки часу)
    proposal_ref: str = ""   # ref на proposal-паспорт
    hour: int = -1           # -1 → з тексту або дефолт 08:00
    minute: int = -1


class RoutineDisableRequest(BaseModel):
    user_id: int
    job: str


def register(router: APIRouter) -> None:
    @router.post("/routines/create")
    async def routines_create_ep(req: RoutineCreateRequest) -> dict[str, Any]:
        from ..routines import parse_schedule_hint

        job = req.job.strip() or (project_proposal(req.proposal_text) or "")
        if not job:
            return {"error": "не вдалося змапити пропозицію на рутину — вкажи job явно"}
        h, m = (req.hour, req.minute)
        if h < 0 or m < 0:
            hint_h, hint_m = parse_schedule_hint(req.proposal_text)
            h = h if h >= 0 else hint_h
            m = m if m >= 0 else hint_m
        return await create_routine(
            req.user_id, job, hour=h, minute=m, proposal_ref=req.proposal_ref
        )

    @router.post("/routines/disable")
    async def routines_disable_ep(req: RoutineDisableRequest) -> dict[str, Any]:
        return await disable_routine(req.user_id, req.job)

    @router.get("/routines/list")
    async def routines_list_ep() -> dict[str, Any]:
        return await list_routines()
