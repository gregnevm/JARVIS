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


class SquadCreate(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    name: str
    parent_id: str | None = None
    kind: str = "team"


class SquadMemberAdd(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    squad_id: str
    user_id: str
    title: str | None = None
    seniority: str | None = None


class RelationshipUpsert(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    src: str
    dst: str
    kind: str
    weight: float = 1.0
    source: str = "declared"


class DelegateUpsert(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    principal_id: str
    persona: dict[str, Any] = {}
    scopes: list[str] = ["read:self"]
    proactive: bool = False


class ProcessCreate(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    owner_user_id: str
    title: str
    steps: list[dict[str, Any]] = []
    squad_id: str | None = None
    template: str | None = None


class ProcessAdvance(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    step_id: str
    status: str


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
    # --- org-граф (squads / relationships / graph / delegate) — passthrough -----

    @router.get("/team/squads")
    async def squads(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get("/team/squads", {"org_id": org_id})

    @router.post("/team/squads")
    async def create_squad(req: SquadCreate, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post("/team/squads", req.model_dump())

    @router.post("/team/squads/member")
    async def add_member(req: SquadMemberAdd, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post("/team/squads/members", req.model_dump())

    @router.get("/team/relationships")
    async def relationships(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get("/team/relationships", {"org_id": org_id})

    @router.post("/team/relationships")
    async def upsert_rel(req: RelationshipUpsert, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post("/team/relationships", req.model_dump())

    @router.get("/team/graph")
    async def graph(request: Request, user_id: str, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get(
            "/team/graph", {"user_id": user_id, "org_id": org_id}
        )

    @router.get("/team/delegate/{principal_id}")
    async def get_delegate(principal_id: str, request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get(
            f"/team/delegates/{principal_id}", {"org_id": org_id}
        )

    @router.put("/team/delegate")
    async def put_delegate(req: DelegateUpsert, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_put("/team/delegates", req.model_dump())

    # --- процеси (BPO, TC-6) — passthrough --------------------------------------

    @router.get("/team/processes")
    async def processes(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get("/team/processes", {"org_id": org_id})

    @router.post("/team/processes")
    async def create_process(req: ProcessCreate, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post("/team/processes", req.model_dump())

    @router.get("/team/processes/{process_id}")
    async def get_process(process_id: str, request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
        return await request.app.state.memory.team_get(
            f"/team/processes/{process_id}", {"org_id": org_id}
        )

    @router.post("/team/processes/{process_id}/advance")
    async def advance_process(process_id: str, req: ProcessAdvance, request: Request) -> dict[str, Any]:
        return await request.app.state.memory.team_post(
            f"/team/processes/{process_id}/advance", req.model_dump()
        )

    # --- групи (presence) --------------------------------------------------------

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
        result = await request.app.state.memory.context_ingest(store)
        # TC-3: спостережений граф — підсилити collaborates_with автор↔згадані.
        if req.subjects:
            await request.app.state.memory.team_post(
                "/team/observe",
                {"org_id": req.org_id, "author": str(req.user_id), "subjects": list(req.subjects)},
            )
        return result
