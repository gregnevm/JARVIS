"""P1 Projects — CRUD (proxy до memory-сервісу) + активний проєкт (Redis).

Скоуп — власні проєкти адміна, що зайшов (auth.user_id). Active project пишемо в
Redis тим самим ключем, що читає агент (gateway/app/projects.py ↔ tools).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..projects import get_active, set_active
from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.projects")


class ProjectBody(BaseModel):
    name: str
    system_prompt: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    archived: bool | None = None


class FileBody(BaseModel):
    name: str
    content: str


class ActiveBody(BaseModel):
    project_id: int | None = None


async def _mem(method: str, path: str, **kw: Any) -> httpx.Response:
    url = f"{settings.memory_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=12.0) as cli:
        return await cli.request(method, url, **kw)


def _bubble(resp: httpx.Response) -> dict[str, Any]:
    """memory-помилку (404/400) піднімаємо як HTTP; інакше — JSON."""
    if resp.status_code >= 400:
        detail = "memory error"
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


def register(router: APIRouter) -> None:
    @router.get("/platform/api/projects")
    async def projects_list(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
        include_archived: bool = False,
    ) -> dict[str, Any]:
        try:
            resp = await _mem(
                "GET", "/projects",
                params={"user_id": auth.user_id, "include_archived": include_archived},
            )
            data = _bubble(resp)
        except httpx.HTTPError as exc:
            logger.warning("projects list failed: %s", exc)
            return {"projects": [], "active_id": None, "error": str(exc)}
        active = await get_active(request.app.state.redis, auth.user_id)
        return {"projects": data.get("projects") or [], "active_id": active}

    @router.post("/platform/api/projects")
    async def projects_create(
        body: ProjectBody, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="name required")
        resp = await _mem(
            "POST", "/projects",
            json={"user_id": auth.user_id, "name": body.name, "system_prompt": body.system_prompt},
        )
        return _bubble(resp)

    # Статичні /active МАЮТЬ бути перед динамічним /{project_id}, інакше FastAPI
    # матчить "active" як project_id (int-валідація падає 422).
    @router.get("/platform/api/projects/active")
    async def project_active_get(
        request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return {"active_id": await get_active(request.app.state.redis, auth.user_id)}

    @router.post("/platform/api/projects/active")
    async def project_active_set(
        body: ActiveBody, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        redis: aioredis.Redis = request.app.state.redis
        if body.project_id is not None:
            resp = await _mem(
                "GET", f"/projects/{body.project_id}", params={"user_id": auth.user_id}
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="project not found")
            _bubble(resp)
        await set_active(redis, auth.user_id, body.project_id)
        return {"ok": True, "active_id": body.project_id}

    @router.get("/platform/api/projects/{project_id}")
    async def projects_get(
        project_id: int, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        resp = await _mem("GET", f"/projects/{project_id}", params={"user_id": auth.user_id})
        return _bubble(resp)

    @router.patch("/platform/api/projects/{project_id}")
    async def projects_update(
        project_id: int, body: ProjectPatch, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        payload = {"user_id": auth.user_id, **body.model_dump(exclude_none=True)}
        resp = await _mem("PATCH", f"/projects/{project_id}", json=payload)
        return _bubble(resp)

    @router.delete("/platform/api/projects/{project_id}")
    async def projects_delete(
        project_id: int, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        resp = await _mem("DELETE", f"/projects/{project_id}", params={"user_id": auth.user_id})
        out = _bubble(resp)
        if await get_active(request.app.state.redis, auth.user_id) == project_id:
            await set_active(request.app.state.redis, auth.user_id, None)
        return out

    @router.post("/platform/api/projects/{project_id}/files")
    async def project_file_add(
        project_id: int, body: FileBody, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        resp = await _mem(
            "POST", f"/projects/{project_id}/files",
            json={"user_id": auth.user_id, "name": body.name, "content": body.content},
        )
        return _bubble(resp)

    @router.delete("/platform/api/projects/{project_id}/files/{file_id}")
    async def project_file_delete(
        project_id: int, file_id: int, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        resp = await _mem(
            "DELETE", f"/projects/{project_id}/files/{file_id}",
            params={"user_id": auth.user_id},
        )
        return _bubble(resp)
