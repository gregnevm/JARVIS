"""P0.4 Memory browser — RAG search + профіль + історія.

Platform admin-only, тож дозволяємо інспектувати будь-який user_id (override через
query/body); за замовчуванням — власний. Search проксі до memory-сервісу,
профіль читаємо напряму з спільного тому (data/profiles/{id}.json).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..config import settings
from .._helpers import require_text
from .auth import PlatformAuth, require_platform_auth, resolve_uid

logger = logging.getLogger("jarvis.gateway.platform.memory")


class SearchBody(BaseModel):
    query: str
    top_k: int = 5
    user_id: int | None = None
    project_id: int | None = None


def _profile_path(user_id: int) -> Path:
    return Path(settings.data_dir) / "profiles" / f"{int(user_id)}.json"


def _notes_path(user_id: int) -> Path:
    return Path(settings.data_dir) / "notes" / f"{int(user_id)}.jsonl"


async def _post_memory(endpoint: str, payload: dict[str, Any]) -> Any:
    """POST `payload` на `{memory_url}/{endpoint}`, повернути розпарсений JSON.

    Узагальнює побайтово ідентичний (з різним лише endpoint/payload) патерн
    `async with httpx.AsyncClient(timeout=12.0) as cli: r = await cli.post(...);
    r.raise_for_status(); data = r.json()`, повторений у `memory_search` та
    `memory_history`. Кидає `httpx.HTTPError` — виклик сам вирішує, як
    логувати/якою заглушкою відповідати (формати fallback-відповідей різні)."""
    async with httpx.AsyncClient(timeout=12.0) as cli:
        r = await cli.post(f"{settings.memory_url.rstrip('/')}/{endpoint}", json=payload)
        r.raise_for_status()
        return r.json()


def register(router: APIRouter) -> None:
    @router.post("/platform/api/memory/search")
    async def memory_search(
        body: SearchBody, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        query = require_text(body.query, field="query")
        uid = resolve_uid(auth, body.user_id)
        top_k = max(1, min(body.top_k, 20))
        payload: dict[str, Any] = {"user_id": uid, "query": query, "top_k": top_k}
        if body.project_id is not None:
            payload["project_id"] = int(body.project_id)
        try:
            data = await _post_memory("search", payload)
        except httpx.HTTPError as exc:
            logger.warning("memory search failed: %s", exc)
            return {
                "results": [],
                "user_id": uid,
                "query": query,
                "project_id": body.project_id,
                "error": str(exc),
            }
        return {"results": data.get("results") or [], "user_id": uid, "query": query,
                "project_id": body.project_id}

    @router.get("/platform/api/memory/notes")
    async def memory_notes(
        auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, user_id)
        lim = max(1, min(limit, 50))
        path = _notes_path(uid)
        if not path.is_file():
            return {"user_id": uid, "notes": []}
        notes: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("notes read %s failed: %s", uid, exc)
            return {"user_id": uid, "notes": [], "error": str(exc)}
        for ln in lines[-lim:]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                notes.append(rec)
        notes.reverse()
        return {"user_id": uid, "notes": notes}

    @router.get("/platform/api/memory/history")
    async def memory_history(
        auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, user_id)
        lim = max(1, min(limit, 100))
        try:
            data = await _post_memory("history", {"user_id": uid, "limit": lim})
        except httpx.HTTPError as exc:
            logger.warning("memory history failed: %s", exc)
            return {"messages": [], "user_id": uid, "error": str(exc)}
        return {"messages": data.get("messages") or [], "user_id": uid}

    @router.get("/platform/api/memory/profile")
    async def memory_profile(
        auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int | None = None,
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, user_id)
        path = _profile_path(uid)
        if not path.is_file():
            return {"user_id": uid, "profile": {}, "exists": False}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("profile read %s failed: %s", uid, exc)
            return {"user_id": uid, "profile": {}, "exists": False, "error": str(exc)}
        return {"user_id": uid, "profile": data if isinstance(data, dict) else {}, "exists": True}
