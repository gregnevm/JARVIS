"""P1 Projects — CRUD (proxy до memory-сервісу) + активний проєкт (Redis).

Скоуп — власні проєкти адміна, що зайшов (auth.user_id). Active project пишемо в
Redis тим самим ключем, що читає агент (gateway/app/projects.py ↔ tools).
"""
from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.service_client import ServiceError, call

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


async def _mem(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Проксі до memory з bubble-семантикою: 2xx → JSON; 4xx/5xx від memory →
    та сама HTTP-помилка назовні (статус + detail); транспортний фейл →
    ServiceError (виклик вирішує — заглушка чи 500, як раніше)."""
    try:
        out = await call(
            settings.memory_url, method, path,
            json=json, params=params, timeout=12.0, service="memory",
        )
    except ServiceError as exc:
        if exc.status is not None:
            raise HTTPException(
                status_code=exc.status, detail=exc.detail or "memory error"
            ) from exc
        raise
    return out if isinstance(out, dict) else {}


def register(router: APIRouter) -> None:
    @router.get("/platform/api/projects")
    async def projects_list(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
        include_archived: bool = False,
    ) -> dict[str, Any]:
        try:
            data = await _mem(
                "GET", "/projects",
                params={"user_id": auth.user_id, "include_archived": include_archived},
            )
        except ServiceError as exc:
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
        return await _mem(
            "POST", "/projects",
            json={"user_id": auth.user_id, "name": body.name, "system_prompt": body.system_prompt},
        )

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
            try:
                await _mem(
                    "GET", f"/projects/{body.project_id}", params={"user_id": auth.user_id}
                )
            except HTTPException as exc:
                if exc.status_code == 404:
                    raise HTTPException(status_code=404, detail="project not found") from exc
                raise
        await set_active(redis, auth.user_id, body.project_id)
        return {"ok": True, "active_id": body.project_id}

    @router.get("/platform/api/projects/{project_id}")
    async def projects_get(
        project_id: int, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await _mem("GET", f"/projects/{project_id}", params={"user_id": auth.user_id})

    @router.patch("/platform/api/projects/{project_id}")
    async def projects_update(
        project_id: int, body: ProjectPatch, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        payload = {"user_id": auth.user_id, **body.model_dump(exclude_none=True)}
        return await _mem("PATCH", f"/projects/{project_id}", json=payload)

    @router.delete("/platform/api/projects/{project_id}")
    async def projects_delete(
        project_id: int, request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        out = await _mem("DELETE", f"/projects/{project_id}", params={"user_id": auth.user_id})
        if await get_active(request.app.state.redis, auth.user_id) == project_id:
            await set_active(request.app.state.redis, auth.user_id, None)
        return out

    @router.post("/platform/api/projects/{project_id}/files")
    async def project_file_add(
        project_id: int, body: FileBody, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await _mem(
            "POST", f"/projects/{project_id}/files",
            json={"user_id": auth.user_id, "name": body.name, "content": body.content},
        )

    @router.delete("/platform/api/projects/{project_id}/files/{file_id}")
    async def project_file_delete(
        project_id: int, file_id: int, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await _mem(
            "DELETE", f"/projects/{project_id}/files/{file_id}",
            params={"user_id": auth.user_id},
        )
