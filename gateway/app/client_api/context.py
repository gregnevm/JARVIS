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

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.passport import (
    CONTEXT_JOB_NAMES,
    Passport,
    Redactor,
    default_redactor,
    normalize_sensitivity,
    normalize_tags,
)

from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.context")

# Подія без summary → провізорний паспорт із цим тегом; bg_job context_summarize
# (CL-3, крок 4) пізніше зведе raw у якісний summary й зніме тег.
PENDING_SUMMARY_TAG = "pending:summary"
_PROVISIONAL_LEN = 240


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


def _uid(ctx: RequestContext) -> int:
    """int-ключ для memory: legacy_uid (Telegram id), фолбек на user_id."""
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id in context")


async def _post_memory(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST на memory `/context/{endpoint}` → JSON. Кидає httpx.HTTPError (ловить виклик)."""
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(
            f"{settings.memory_url.rstrip('/')}/context/{endpoint}", json=payload
        )
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


async def _post_tools(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """POST на tools `{path}` (context-job). Довгий таймаут — job кличе Ollama."""
    async with httpx.AsyncClient(timeout=300.0) as cli:
        r = await cli.post(f"{settings.tools_url.rstrip('/')}{path}", params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


def _build_store(ev: ContextEvent, uid: int, org_id: str, redactor: Redactor) -> dict[str, Any]:
    """Будує ФІНІШНИЙ паспорт (серверна редакція + нормалізація тегів) перед store.

    Дві швидкості (CONTEXT_MODULE §2):
      * fast — є `summary` → редагуємо й шлемо;
      * raw  — лише `content` → провізорний summary з excerpt, raw у payload,
               тег `pending:summary` (bg_job дозведе пізніше).
    Порожня подія (ні summary, ні content) → summary="" → виклик рахує як failed.
    """
    kind = (ev.kind or "note").strip() or "note"
    payload = dict(ev.payload or {})
    tags = list(ev.tags)
    raw_summary = (ev.summary or "").strip()
    if raw_summary:
        summary = raw_summary
    else:
        content = (ev.content or "").strip()
        summary = content[:_PROVISIONAL_LEN]
        if content:
            payload.setdefault("raw", content)
            tags.append(PENDING_SUMMARY_TAG)
    passport = Passport(
        kind=kind,
        summary=summary,
        tags=normalize_tags(tags, kind),
        sensitivity=normalize_sensitivity(ev.sensitivity),
        source=ev.source,
        ref=ev.ref,
        event_id=ev.event_id,
        event_ts=ev.event_ts,
        payload=payload,
    )
    # Серверна (друга) редакція: вирізає секрети/PII, прибирає raw для health/finance.
    passport = redactor.redact_passport(passport)
    store = passport.to_store()
    store["user_id"] = uid
    store["org_id"] = org_id
    return store


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
            except httpx.HTTPError as exc:
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
        except httpx.HTTPError as exc:
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
        except httpx.HTTPError as exc:
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
        except httpx.HTTPError as exc:
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
        except httpx.HTTPError as exc:
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
        except httpx.HTTPError as exc:
            logger.warning("context job %s failed: %s", name, type(exc).__name__)
            raise HTTPException(status_code=502, detail="tools unreachable") from exc
