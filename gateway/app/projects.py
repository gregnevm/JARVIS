"""Активний проєкт користувача — Redis-стан (P1), спільний із tools.

Той самий ключ, що читає агент: `jarvis:project:{user_id}` (див.
tools/app/projects.py). Gateway і tools на одному Redis, тож пишемо напряму —
Telegram `/project` і Platform UI керують активним проєктом без зайвого хопа.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger("jarvis.gateway.projects")

_KEY = "jarvis:project:"


async def get_active(redis: aioredis.Redis | None, user_id: int) -> int | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(f"{_KEY}{int(user_id)}")
    except Exception as exc:  # noqa: BLE001 — стан проєкту не критичний
        logger.debug("active project read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


async def set_active(redis: aioredis.Redis, user_id: int, project_id: int | None) -> None:
    key = f"{_KEY}{int(user_id)}"
    if project_id is None:
        await redis.delete(key)
    else:
        await redis.set(key, str(int(project_id)))


# --- memory-сервіс CRUD (для Telegram /project; Platform має власний проксі) ---
async def mem_list(user_id: int) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(f"{settings.memory_url.rstrip('/')}/projects", params={"user_id": user_id})
            r.raise_for_status()
            return list(r.json().get("projects", []))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("projects list failed: %s", exc)
        return []


async def mem_create(user_id: int, name: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.post(
                f"{settings.memory_url.rstrip('/')}/projects",
                json={"user_id": user_id, "name": name},
            )
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("project create failed: %s", exc)
        return None


async def mem_get(user_id: int, project_id: int) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(
                f"{settings.memory_url.rstrip('/')}/projects/{int(project_id)}",
                params={"user_id": user_id},
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("project get failed: %s", exc)
        return None
