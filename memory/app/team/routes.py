"""Team-ecosystem routes (Стовп D, TC-0) — squads / relationships / delegates / graph.

Dumb store поверх `db.py` CRUD: персист + читання org-scoped. Граф будується доменом
(`jarvis_core.orggraph.OrgGraph`) із трьох наборів — повертаємо зібрані сусіди/ланцюг
менеджерів для UI-візуалізації, без дублювання логіки в memory (P8).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID
from jarvis_core.orggraph import OrgGraph, Relationship, Squad, SquadMember
from jarvis_core.orggraph.models import REL_KINDS, SQUAD_KINDS
from jarvis_core.process import Process, advance, is_complete, ready_steps

logger = logging.getLogger("jarvis.memory.team")

router = APIRouter(prefix="/team", tags=["team"])


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


class GroupConsent(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    chat_id: int
    ingest: str = "off"
    title: str | None = None
    squad_id: str | None = None
    consented_by: str | None = None


class GroupMemberUpsert(BaseModel):
    chat_id: int
    telegram_id: int
    user_id: str | None = None


class ObserveInteraction(BaseModel):
    org_id: str = DEFAULT_ORG_ID
    author: str
    subjects: list[str] = []
    delta: float = 1.0


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


# Рівні згоди на обробку групи (дзеркалить gateway bot.group.INGEST_LEVELS).
_INGEST_LEVELS = frozenset({"off", "addressed", "ambient"})


def _db(request: Request) -> Any:
    return request.app.state.db


async def _load_graph(db: Any, org_id: str) -> OrgGraph:
    squads = [
        Squad(id=s["id"], org_id=s["org_id"], name=s["name"], parent_id=s["parent_id"], kind=s["kind"])
        for s in await db.list_squads(org_id)
    ]
    members = [
        SquadMember(squad_id=m["squad_id"], user_id=m["user_id"], title=m["title"], seniority=m["seniority"])
        for m in await db.list_squad_members(org_id)
    ]
    rels = [
        Relationship(org_id=r["org_id"], src_user_id=r["src_user_id"], dst_user_id=r["dst_user_id"],
                     kind=r["kind"], weight=r["weight"], source=r["source"])
        for r in await db.list_relationships(org_id)
    ]
    return OrgGraph(org_id, squads, members, rels)


@router.post("/squads")
async def create_squad(req: SquadCreate, request: Request) -> dict[str, Any]:
    if req.kind not in SQUAD_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(SQUAD_KINDS)}")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name required")
    return await _db(request).create_squad(
        org_id=req.org_id, name=req.name.strip(), parent_id=req.parent_id, kind=req.kind
    )


@router.get("/squads")
async def list_squads(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    squads = await _db(request).list_squads(org_id)
    members = await _db(request).list_squad_members(org_id)
    by_squad: dict[str, list[dict[str, Any]]] = {}
    for m in members:
        by_squad.setdefault(m["squad_id"], []).append(m)
    for s in squads:
        s["members"] = by_squad.get(s["id"], [])
    return {"squads": squads, "org_id": org_id}


@router.post("/squads/members")
async def add_member(req: SquadMemberAdd, request: Request) -> dict[str, Any]:
    ok = await _db(request).add_squad_member(
        squad_id=req.squad_id, user_id=req.user_id, title=req.title, seniority=req.seniority
    )
    return {"ok": bool(ok)}


@router.post("/relationships")
async def upsert_relationship(req: RelationshipUpsert, request: Request) -> dict[str, Any]:
    if req.kind not in REL_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(REL_KINDS)}")
    ok = await _db(request).upsert_relationship(
        org_id=req.org_id, src=req.src, dst=req.dst, kind=req.kind,
        weight=req.weight, source=req.source,
    )
    return {"ok": bool(ok)}


@router.get("/relationships")
async def list_relationships(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    return {"relationships": await _db(request).list_relationships(org_id), "org_id": org_id}


@router.post("/observe")
async def observe(req: ObserveInteraction, request: Request) -> dict[str, Any]:
    """Підсилює observed-ребра `collaborates_with` між автором і суб'єктами (§3.3)."""
    from jarvis_core.orggraph import interaction_edges

    bumped: list[dict[str, Any]] = []
    for src, dst in interaction_edges(req.author, req.subjects):
        w = await _db(request).bump_relationship(
            org_id=req.org_id, src=src, dst=dst, kind="collaborates_with", delta=req.delta
        )
        bumped.append({"src": src, "dst": dst, "weight": w})
    return {"bumped": bumped}


@router.get("/graph")
async def graph(request: Request, user_id: str, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    """Сусіди + ланцюг менеджерів + squads вузла — для UI-візуалізації (§10)."""
    g = await _load_graph(_db(request), org_id)
    return {
        "user_id": user_id,
        "org_id": org_id,
        "squads": sorted(g.squads_of(user_id)),
        "manager_chain": g.manager_chain(user_id),
        "manages": sorted(g.neighbors(user_id, "manages")),
        "reports": sorted(g.inbound(user_id, "reports_to")),
        "collaborators": sorted(g.neighbors(user_id, "collaborates_with")),
    }


@router.get("/delegates/{principal_id}")
async def get_delegate(principal_id: str, request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    rec = await _db(request).get_delegate(org_id, principal_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="delegate not found")
    return rec


@router.put("/delegates")
async def upsert_delegate(req: DelegateUpsert, request: Request) -> dict[str, Any]:
    return await _db(request).upsert_delegate(
        org_id=req.org_id, principal_id=req.principal_id,
        persona=req.persona, scopes=req.scopes, proactive=req.proactive,
    )


@router.get("/groups")
async def list_groups(request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    return {"groups": await _db(request).list_groups(org_id), "org_id": org_id}


@router.get("/groups/{chat_id}")
async def get_group(chat_id: int, request: Request) -> dict[str, Any]:
    rec = await _db(request).get_group(chat_id)
    # Незареєстрована група = дефолт off (privacy-first §8.1) — не 404, щоб gateway
    # просто мовчав без зайвої гілки помилки.
    return rec or {"chat_id": chat_id, "ingest": "off", "org_id": None, "squad_id": None, "title": None}


@router.post("/groups/consent")
async def group_consent(req: GroupConsent, request: Request) -> dict[str, Any]:
    if req.ingest not in _INGEST_LEVELS:
        raise HTTPException(status_code=400, detail=f"ingest must be one of {sorted(_INGEST_LEVELS)}")
    return await _db(request).upsert_group(
        chat_id=req.chat_id, org_id=req.org_id, title=req.title,
        ingest=req.ingest, squad_id=req.squad_id, consented_by=req.consented_by,
    )


@router.post("/groups/members")
async def group_member(req: GroupMemberUpsert, request: Request) -> dict[str, Any]:
    ok = await _db(request).upsert_group_member(
        chat_id=req.chat_id, telegram_id=req.telegram_id, user_id=req.user_id
    )
    return {"ok": bool(ok)}


# --- процеси (BPO, TC-6) -----------------------------------------------------

@router.post("/processes")
async def create_process(req: ProcessCreate, request: Request) -> dict[str, Any]:
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title required")
    # стартовий статус виводимо доменом: якщо є непорожні кроки — лишаємо draft до advance.
    rec = await _db(request).create_process(
        org_id=req.org_id, owner_user_id=req.owner_user_id, title=req.title.strip(),
        steps=req.steps, squad_id=req.squad_id, template=req.template,
    )
    proc = Process.from_dict(rec)
    rec["ready"] = [s.id for s in ready_steps(proc)]
    return rec


@router.get("/processes")
async def list_processes(request: Request, org_id: str = DEFAULT_ORG_ID, limit: int = 50) -> dict[str, Any]:
    return {"processes": await _db(request).list_processes(org_id, limit), "org_id": org_id}


@router.get("/processes/{process_id}")
async def get_process(process_id: str, request: Request, org_id: str = DEFAULT_ORG_ID) -> dict[str, Any]:
    rec = await _db(request).get_process(process_id, org_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="process not found")
    proc = Process.from_dict(rec)
    rec["ready"] = [s.id for s in ready_steps(proc)]
    return rec


@router.post("/processes/{process_id}/advance")
async def advance_process(process_id: str, req: ProcessAdvance, request: Request) -> dict[str, Any]:
    """Перехід кроку через доменну машину станів (engine.advance) + персист."""
    rec = await _db(request).get_process(process_id, req.org_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="process not found")
    proc = Process.from_dict(rec)
    if not advance(proc, req.step_id, req.status):
        raise HTTPException(status_code=400, detail="invalid step_id or status (no change)")
    await _db(request).update_process(
        process_id=process_id, org_id=req.org_id,
        steps=[s.to_dict() for s in proc.steps], status=proc.status,
    )
    out = proc.to_dict()
    out["ready"] = [s.id for s in ready_steps(proc)]
    out["complete"] = is_complete(proc)
    return out
