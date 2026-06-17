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
