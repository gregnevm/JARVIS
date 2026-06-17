"""Стовп D Platform tab «Команда / Граф» (TEAM_ECOSYSTEM TC-0, §10).

Тонкий проксі gateway-platform → ToolsClient → tools `/team/*` → memory. Дерево
squads + ребра графа + lookup сусідів/менеджерського ланцюга для візуалізації.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID
from .auth import PlatformAuth, require_platform_auth, resolve_context


class SquadBody(BaseModel):
    name: str
    parent_id: str | None = None
    kind: str = "team"


class MemberBody(BaseModel):
    squad_id: str
    user_id: str
    title: str | None = None
    seniority: str | None = None


class RelationshipBody(BaseModel):
    src: str
    dst: str
    kind: str


class ProcessBody(BaseModel):
    owner_user_id: str
    title: str
    steps: list[dict[str, Any]] = []
    squad_id: str | None = None
    template: str | None = None


class AdvanceBody(BaseModel):
    step_id: str
    status: str


def _org(request: Request, auth: PlatformAuth) -> str:
    return resolve_context(auth).org_id or DEFAULT_ORG_ID


def register(router: APIRouter) -> None:
    @router.get("/platform/api/team/squads")
    async def squads(request: Request, auth: PlatformAuth = Depends(require_platform_auth)) -> dict[str, Any]:
        return await request.app.state.tools.team_squads(_org(request, auth))

    @router.post("/platform/api/team/squads")
    async def create_squad(
        body: SquadBody, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_create_squad(
            {"org_id": _org(request, auth), **body.model_dump()}
        )

    @router.post("/platform/api/team/members")
    async def add_member(
        body: MemberBody, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_add_member(
            {"org_id": _org(request, auth), **body.model_dump()}
        )

    @router.get("/platform/api/team/relationships")
    async def relationships(request: Request, auth: PlatformAuth = Depends(require_platform_auth)) -> dict[str, Any]:
        return await request.app.state.tools.team_relationships(_org(request, auth))

    @router.post("/platform/api/team/relationships")
    async def upsert_rel(
        body: RelationshipBody, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_upsert_relationship(
            {"org_id": _org(request, auth), **body.model_dump()}
        )

    @router.get("/platform/api/team/graph")
    async def graph(
        request: Request, user_id: str, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_graph(user_id, _org(request, auth))

    # процеси (BPO §10)
    @router.get("/platform/api/processes")
    async def processes(request: Request, auth: PlatformAuth = Depends(require_platform_auth)) -> dict[str, Any]:
        return await request.app.state.tools.team_processes(_org(request, auth))

    @router.post("/platform/api/processes")
    async def create_process(
        body: ProcessBody, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_create_process(
            {"org_id": _org(request, auth), **body.model_dump()}
        )

    @router.get("/platform/api/processes/{process_id}")
    async def get_process(
        process_id: str, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_get_process(process_id, _org(request, auth))

    @router.post("/platform/api/processes/{process_id}/advance")
    async def advance_process(
        process_id: str, body: AdvanceBody, request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        return await request.app.state.tools.team_advance_process(
            process_id, {"org_id": _org(request, auth), **body.model_dump()}
        )
