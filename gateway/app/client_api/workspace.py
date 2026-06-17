"""Client-API: chats (sessions/history) + projects — тонкий проксі до memory.

Завершує контракт CL-1.3 для нативних клієнтів: список чатів/історія + CRUD проєктів
під єдиною auth (resolve_client_context), org-scoped (uid із RequestContext). Бізнес-логіка
лишається в memory (S3) — тут лише I/O.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.workspace")


class HistoryBody(BaseModel):
    limit: int = 30


class ProjectBody(BaseModel):
    name: str
    system_prompt: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    archived: bool | None = None


def _uid(ctx: RequestContext) -> int:
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id")


async def _mem_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.get(f"{settings.memory_url.rstrip('/')}{path}", params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


async def _mem(method: str, path: str, payload: dict[str, Any] | None = None,
               params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.request(method, f"{settings.memory_url.rstrip('/')}{path}",
                              json=payload, params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


def register(router: APIRouter) -> None:
    # ---- chats: sessions + history ----
    @router.get("/sessions")
    async def sessions(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get("/sessions", {"user_id": _uid(ctx), "limit": 30})
        except httpx.HTTPError:
            return {"sessions": [], "error": "memory_unreachable"}

    @router.post("/history")
    async def history(body: HistoryBody,
                      ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("POST", "/history", {"user_id": _uid(ctx), "limit": body.limit})
        except httpx.HTTPError:
            return {"messages": [], "error": "memory_unreachable"}

    # ---- projects CRUD ----
    @router.get("/projects")
    async def projects_list(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get("/projects", {"user_id": _uid(ctx)})
        except httpx.HTTPError:
            return {"projects": [], "error": "memory_unreachable"}

    @router.post("/projects")
    async def projects_create(body: ProjectBody,
                              ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("POST", "/projects",
                              {"user_id": _uid(ctx), "name": body.name,
                               "system_prompt": body.system_prompt})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc

    @router.get("/projects/{project_id}")
    async def projects_get(project_id: int,
                           ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get(f"/projects/{project_id}", {"user_id": _uid(ctx)})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc

    @router.patch("/projects/{project_id}")
    async def projects_update(project_id: int, body: ProjectPatch,
                              ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        payload: dict[str, Any] = {"user_id": _uid(ctx)}
        if body.name is not None:
            payload["name"] = body.name
        if body.system_prompt is not None:
            payload["system_prompt"] = body.system_prompt
        if body.archived is not None:
            payload["archived"] = body.archived
        try:
            return await _mem("PATCH", f"/projects/{project_id}", payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc

    @router.delete("/projects/{project_id}")
    async def projects_delete(project_id: int,
                              ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("DELETE", f"/projects/{project_id}", params={"user_id": _uid(ctx)})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc
