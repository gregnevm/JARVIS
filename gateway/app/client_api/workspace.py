"""Client-API: chats (sessions/history) + projects — тонкий проксі до memory.

Завершує контракт CL-1.3 для нативних клієнтів: список чатів/історія + CRUD проєктів
під єдиною auth (resolve_client_context), org-scoped (uid із RequestContext). Бізнес-логіка
лишається в memory (S3) — тут лише I/O.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .deps import context_uid as _uid, resolve_client_context

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


async def _mem_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    return await call_dict(
        settings.memory_url, "GET", path, params=params, timeout=15.0, service="memory"
    )


async def _mem(method: str, path: str, payload: dict[str, Any] | None = None,
               params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await call_dict(
        settings.memory_url, method, path,
        json=payload, params=params, timeout=15.0, service="memory",
    )


def register(router: APIRouter) -> None:
    # ---- chats: sessions + history ----
    @router.get("/sessions")
    async def sessions(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get("/sessions", {"user_id": _uid(ctx), "limit": 30})
        except ServiceError:
            return {"sessions": [], "error": "memory_unreachable"}

    @router.post("/history")
    async def history(body: HistoryBody,
                      ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("POST", "/history", {"user_id": _uid(ctx), "limit": body.limit})
        except ServiceError:
            return {"messages": [], "error": "memory_unreachable"}

    # ---- projects CRUD ----
    @router.get("/projects")
    async def projects_list(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get("/projects", {"user_id": _uid(ctx)})
        except ServiceError:
            return {"projects": [], "error": "memory_unreachable"}

    @router.post("/projects")
    async def projects_create(body: ProjectBody,
                              ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("POST", "/projects",
                              {"user_id": _uid(ctx), "name": body.name,
                               "system_prompt": body.system_prompt})
        except ServiceError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc

    @router.get("/projects/{project_id}")
    async def projects_get(project_id: int,
                           ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem_get(f"/projects/{project_id}", {"user_id": _uid(ctx)})
        except ServiceError as exc:
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
        except ServiceError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc

    @router.delete("/projects/{project_id}")
    async def projects_delete(project_id: int,
                              ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        try:
            return await _mem("DELETE", f"/projects/{project_id}", params={"user_id": _uid(ctx)})
        except ServiceError as exc:
            raise HTTPException(status_code=502, detail="memory unreachable") from exc
