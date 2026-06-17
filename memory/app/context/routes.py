"""Context Passport routes (P9/P10/C1) — dumb store+retrieve поверх `context_events`.

Винесено з `main.py` у sub-package (docs/CONTEXT_MODULE.md §3): memory — лише
персист + embed. Доменна логіка (нормалізація тегів, редакція) — у `jarvis_core.passport`
(SSOT, дедуп). Тут НЕ дублюємо таксономію тегів.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID
from jarvis_core.passport import normalize_sensitivity, normalize_tags

logger = logging.getLogger("jarvis.memory.context")

router = APIRouter(prefix="/context", tags=["context"])


class ContextIngestRequest(BaseModel):
    user_id: int
    kind: str = "note"
    summary: str | None = None
    content: str | None = None  # сире (редаговане); фолбек для summary
    tags: list[str] = []
    source: str | None = None
    sensitivity: str = "personal"
    ref: str | None = None
    event_id: str | None = None
    event_ts: str | None = None
    payload: dict[str, Any] = {}
    org_id: str = DEFAULT_ORG_ID


class ContextSearchRequest(BaseModel):
    user_id: int
    query: str
    top_k: int = 8
    tags: list[str] | None = None
    since: str | None = None


class ContextRecentRequest(BaseModel):
    user_id: int
    limit: int = 20
    kind: str | None = None
    tags: list[str] | None = None


class ContextPurgeRequest(BaseModel):
    user_id: int
    before: str | None = None
    kind: str | None = None


class ContextLedgerRequest(BaseModel):
    user_id: int
    recent_limit: int = 20


class ContextPendingRequest(BaseModel):
    user_id: int
    limit: int = 20


class ContextUpdateRequest(BaseModel):
    id: int
    user_id: int
    summary: str
    tags: list[str] = []
    kind: str = "note"


async def _embed_or_none(request: Request, text: str) -> list[float] | None:
    """Embedding best-effort: збір не падає, якщо Ollama лежить (P1 offline-first)."""
    try:
        result: list[float] = await request.app.state.embedder.embed(text)
        return result
    except Exception as exc:  # noqa: BLE001 — embedding нефатальний для збору
        logger.warning("context embed failed (stored without vector): %s", exc)
        return None


async def _embed_or_502(request: Request, text: str) -> list[float]:
    try:
        result: list[float] = await request.app.state.embedder.embed(text)
        return result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"embed failed: {exc}") from exc


@router.post("/ingest")
async def context_ingest(req: ContextIngestRequest, request: Request) -> dict[str, Any]:
    """P9: персист паспорта (+ embed summary). Теги нормалізує спільний
    `jarvis_core.passport.normalize_tags` (P10-інваріант kind-тег)."""
    summary = (req.summary or req.content or "").strip()
    if not summary:
        raise HTTPException(status_code=400, detail="summary or content required")
    summary = summary[:4000]
    kind = (req.kind or "note").strip() or "note"
    tags = normalize_tags(req.tags, kind)

    embedding = await _embed_or_none(request, summary)
    res = await request.app.state.db.add_context_event(
        user_id=req.user_id,
        kind=kind,
        summary=summary,
        tags=tags,
        embedding=embedding,
        org_id=req.org_id or DEFAULT_ORG_ID,
        source=req.source,
        sensitivity=normalize_sensitivity(req.sensitivity),
        ref=req.ref,
        event_id=req.event_id,
        event_ts=req.event_ts,
        payload=req.payload,
    )
    return {
        "id": res.get("id"),
        "inserted": res.get("inserted", False),
        "embedded": embedding is not None,
        "kind": kind,
        "tags": tags,
    }


@router.post("/search")
async def context_search(req: ContextSearchRequest, request: Request) -> dict[str, Any]:
    vec = await _embed_or_502(request, req.query)
    top_k = max(1, min(req.top_k, 50))
    results = await request.app.state.db.search_context(
        req.user_id, vec, top_k, tags=req.tags, since=req.since
    )
    return {"results": results}


@router.post("/recent")
async def context_recent(req: ContextRecentRequest, request: Request) -> dict[str, Any]:
    limit = max(1, min(req.limit, 200))
    items = await request.app.state.db.recent_context(
        req.user_id, limit, kind=req.kind, tags=req.tags
    )
    return {"events": items}


@router.post("/purge")
async def context_purge(req: ContextPurgeRequest, request: Request) -> dict[str, Any]:
    deleted = await request.app.state.db.purge_context(
        req.user_id, before=req.before, kind=req.kind
    )
    return {"deleted": deleted}


@router.post("/ledger")
async def context_ledger(req: ContextLedgerRequest, request: Request) -> dict[str, Any]:
    """Журнал прозорості (E3): агрегати + останні паспорти користувача."""
    limit = max(1, min(req.recent_limit, 100))
    return await request.app.state.db.context_ledger(req.user_id, recent_limit=limit)


@router.post("/pending")
async def context_pending(req: ContextPendingRequest, request: Request) -> dict[str, Any]:
    """Паспорти, що чекають дозведення (`pending:summary`) — для job context_summarize."""
    limit = max(1, min(req.limit, 200))
    items = await request.app.state.db.pending_context(req.user_id, limit)
    return {"events": items}


@router.post("/update")
async def context_update(req: ContextUpdateRequest, request: Request) -> dict[str, Any]:
    """Оновлює summary+tags паспорта (+ re-embed). Використовує context_summarize."""
    summary = req.summary.strip()
    if not summary:
        raise HTTPException(status_code=400, detail="summary required")
    tags = normalize_tags(req.tags, req.kind)
    embedding = await _embed_or_none(request, summary[:4000])
    ok = await request.app.state.db.update_context_event(
        req.id, req.user_id, summary=summary[:4000], tags=tags, embedding=embedding
    )
    if not ok:
        raise HTTPException(status_code=404, detail="event not found")
    return {"ok": True, "embedded": embedding is not None, "tags": tags}
