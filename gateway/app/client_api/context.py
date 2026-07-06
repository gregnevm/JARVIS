"""Client-API: збір та ретрив контексту (Стовп C / CL-3, культура P9/P10/C1).

Єдиний вхід для будь-якого клієнта (APK, скрипт на хості, платформа) → memory
`/context/*`. Кожна подія несе паспорт (kind + summary + namespaced tags); memory
ембедить summary й зберігає. Усе за прапором `ENABLE_CONTEXT_API` (S2: self-hosted
без прапора не зачеплений). Auth — спільний `resolve_client_context` (JWT/initData/Basic).

Org-scoped: `user_id` для memory = `ctx.legacy_uid` (int-ключ партиціювання), `org_id`
= `ctx.org_id`. payload (сире) НІКОЛИ не логимо — лише лічильники (клас token-leak).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.passport import (
    CONTEXT_JOB_NAMES,
    Redactor,
    build_store_event,
    default_redactor,
)
from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .deps import context_uid as _uid
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.context")


class ContextEvent(BaseModel):
    kind: str = "note"
    summary: str | None = None
    content: str | None = None
    tags: list[str] = []
    source: str | None = None
    sensitivity: str = "personal"
    ref: str | None = None
    event_id: str | None = None
    event_ts: str | None = None
    payload: dict[str, Any] = {}


class IngestBatch(BaseModel):
    events: list[ContextEvent]


class ContextSearchBody(BaseModel):
    query: str
    top_k: int = 8
    tags: list[str] | None = None
    since: str | None = None


class ContextRecentBody(BaseModel):
    limit: int = 20
    kind: str | None = None
    tags: list[str] | None = None


class ContextPurgeBody(BaseModel):
    before: str | None = None
    kind: str | None = None


class ContextLedgerBody(BaseModel):
    recent_limit: int = 20


def _require_enabled() -> None:
    if not settings.enable_context_api:
        raise HTTPException(status_code=404, detail="context API disabled")


async def _post_memory(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST на memory `/context/{endpoint}` → JSON. Кидає ServiceError (ловить виклик)."""
    return await call_dict(
        settings.memory_url, "POST", f"/context/{endpoint}",
        json=payload, timeout=15.0, service="memory",
    )


async def _post_tools(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """POST на tools `{path}` (context-job). Довгий таймаут — job кличе Ollama."""
    return await call_dict(
        settings.tools_url, "POST", path,
        params=params, timeout=300.0, service="tools",
    )


def _build_store(ev: ContextEvent, uid: int, org_id: str, redactor: Redactor) -> dict[str, Any]:
    """Мапить ContextEvent → фінішний store-паспорт. Домен (дві швидкості,
    редакція, нормалізація) — у `jarvis_core.passport.build_store_event` (R3, S3)."""
    return build_store_event(
        user_id=uid,
        org_id=org_id,
        redactor=redactor,
        kind=ev.kind,
        summary=ev.summary,
        content=ev.content,
        tags=list(ev.tags),
        sensitivity=ev.sensitivity,
        source=ev.source,
        ref=ev.ref,
        event_id=ev.event_id,
        event_ts=ev.event_ts,
        payload=ev.payload,
    )


def register(router: APIRouter) -> None:
    @router.post("/ingest/events")
    async def ingest_events(
        body: IngestBatch, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        _require_enabled()
        if not body.events:
            return {"accepted": 0, "duplicates": 0, "failed": 0, "ids": []}
        if len(body.events) > settings.context_ingest_max_batch:
            raise HTTPException(
                status_code=413,
                detail=f"batch too large (max {settings.context_ingest_max_batch})",
            )
        uid = _uid(ctx)
        redactor = default_redactor()
        accepted = duplicates = failed = 0
        ids: list[int] = []
        for ev in body.events:
            store = _build_store(ev, uid, ctx.org_id, redactor)
            if not store["summary"]:
                failed += 1  # порожня подія (ні summary, ні content)
                continue
            try:
                res = await _post_memory("ingest", store)
            except ServiceError as exc:
                failed += 1
                # Лише лічильник/тип помилки — НЕ payload (anti token/PII leak).
                logger.warning("context ingest failed for one event: %s", type(exc).__name__)
                continue
            if res.get("inserted"):
                accepted += 1
            else:
                duplicates += 1
            if res.get("id") is not None:
                ids.append(int(res["id"]))
        return {"accepted": accepted, "duplicates": duplicates, "failed": failed, "ids": ids}

    @router.post("/context/search")
    async def context_search(
        body: ContextSearchBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        _require_enabled()
        payload = {
            "user_id": _uid(ctx),
            "query": body.query,
            "top_k": body.top_k,
            "tags": body.tags,
            "since": body.since,
        }
        try:
            data = await _post_memory("search", payload)
        except ServiceError as exc:
            logger.warning("context search failed: %s", type(exc).__name__)
            return {"results": [], "error": "memory_unreachable"}
        return {"results": data.get("results") or []}

    @router.post("/context/recent")
    async def context_recent(
        body: ContextRecentBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        _require_enabled()
        payload = {
            "user_id": _uid(ctx),
            "limit": body.limit,
            "kind": body.kind,
            "tags": body.tags,
        }
        try:
            data = await _post_memory("recent", payload)
        except ServiceError as exc:
            logger.warning("context recent failed: %s", type(exc).__name__)
            return {"events": [], "error": "memory_unreachable"}
        return {"events": data.get("events") or []}

    @router.post("/context/purge")
    async def context_purge(
        body: ContextPurgeBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        _require_enabled()
        payload = {"user_id": _uid(ctx), "before": body.before, "kind": body.kind}
        try:
            data = await _post_memory("purge", payload)
        except ServiceError as exc:
            logger.warning("context purge failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="memory unreachable") from exc
        return {"deleted": int(data.get("deleted", 0))}

    @router.post("/context/ledger")
    async def context_ledger(
        body: ContextLedgerBody, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        """Журнал прозорості (E3): що зібрано/збережено для цього користувача."""
        _require_enabled()
        try:
            return await _post_memory(
                "ledger", {"user_id": _uid(ctx), "recent_limit": body.recent_limit}
            )
        except ServiceError as exc:
            logger.warning("context ledger failed: %s", type(exc).__name__)
            return {"total": 0, "by_kind": {}, "by_source": {}, "recent": [], "error": "memory_unreachable"}

    @router.post("/context/jobs/{name}")
    async def context_run_job(
        name: str, ctx: RequestContext = Depends(resolve_client_context)
    ) -> dict[str, Any]:
        """Проксі тригера context-maintenance job у tools (ADR-008: запуск із нагляду —
        напр. власний Task Scheduler/cron б'є цей ендпоінт). Org-scoped по ctx."""
        _require_enabled()
        if name not in CONTEXT_JOB_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown context job: {name}")
        try:
            return await _post_tools(f"/context/jobs/{name}", {"user_id": _uid(ctx)})
        except ServiceError as exc:
            logger.warning("context job %s failed: %s", name, type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc
