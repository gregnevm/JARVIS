"""Team-ecosystem proxy (Стовп D) — gateway→tools→memory для груп/графа.

Тонкий passthrough до memory `/team/*` (+ `/context/ingest` для ambient-збору груп).
Домен (граф/видимість/паспорт) — у `jarvis_core`; тут лише I/O-маршрут (P8/S3).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID
from jarvis_core.passport import Passport, normalize_tags


class GroupMemberSeen(BaseModel):
    chat_id: int
    telegram_id: int
    user_id: str | None = None


class GroupCollect(BaseModel):
    chat_id: int
    user_id: int                      # автор (Telegram id) — власник паспорта
    summary: str
    org_id: str = DEFAULT_ORG_ID
    from_name: str = ""
    subjects: list[str] = []
    squad_id: str | None = None


def register(router: APIRouter) -> None:
    @router.get("/team/group/{chat_id}/ingest")
    async def group_ingest(chat_id: int, request: Request) -> dict[str, Any]:
        rec = await request.app.state.memory.team_get(f"/team/groups/{chat_id}")
        return {"chat_id": chat_id, "ingest": str(rec.get("ingest") or "off"),
                "org_id": rec.get("org_id"), "squad_id": rec.get("squad_id")}

    @router.post("/team/group/member")
    async def group_member(req: GroupMemberSeen, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post(
            "/team/groups/members",
            {"chat_id": req.chat_id, "telegram_id": req.telegram_id, "user_id": req.user_id},
        )

    @router.post("/team/group/collect")
    async def group_collect(req: GroupCollect, request: Request) -> dict[str, Any]:
        """Ambient-збір групового повідомлення в паспорт (visibility=squad, group_ref)."""
        summary = (req.summary or "").strip()
        if not summary:
            return {"inserted": False, "skipped": "empty"}
        tags = normalize_tags(
            ["kind:group_msg", f"group:{req.chat_id}", f"person:{req.from_name or req.user_id}"],
            "group_msg",
        )
        p = Passport(
            kind="group_msg",
            summary=summary[:4000],
            tags=tags,
            sensitivity="personal",
            source="tg_group",
            subjects=[str(s) for s in req.subjects],
            visibility="squad",
            group_ref=req.chat_id,
        )
        store = p.to_store()
        store["user_id"] = req.user_id
        store["org_id"] = req.org_id
        return await request.app.state.memory.context_ingest(store)
