"""P0.2 Overview — health + metrics + settings snapshot для `/platform`.

Об'єднує tools `/dashboard` (Ollama, моделі, turn p50/p95, RAG hit-rate),
runtime-stack (host-agent/docker) і HTTP-проби сервісів. Reuse адмінських
хелперів — щоб не дублювати проби.
"""
from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request

from ..admin_panel import _safe_health_prev, probe_services
from ..health_watch import _fetch_stack, _labels
from ..services import ServicesClient
from .auth import PlatformAuth, require_platform_auth


def _metrics_snapshot(core: dict[str, Any]) -> dict[str, Any]:
    """Витягує observability-метрики з dashboard payload (tools/app/metrics.py)."""
    m = core.get("metrics") if isinstance(core, dict) else None
    if not isinstance(m, dict):
        return {"turn_ms": {}, "rag_hit_rate": 0.0, "rag_queries": 0, "tools": {}}
    return {
        "turn_ms": m.get("turn_ms") or {},
        "rag_hit_rate": m.get("rag_hit_rate", 0.0),
        "rag_queries": m.get("rag_queries", 0),
        "tools": m.get("tools") or {},
    }


def _models_snapshot(core: dict[str, Any]) -> dict[str, Any]:
    return {
        "ollama_host": core.get("ollama_host") or "—",
        "ollama_up": bool(core.get("ollama_up")),
        "chat_model": core.get("chat_model"),
        "agent_model": core.get("agent_model"),
        "vision_model": core.get("vision_model") or "—",
        "embed_model": core.get("embed_model") or "—",
    }


def register(router: APIRouter) -> None:
    @router.get("/platform/api/overview")
    async def platform_overview(
        request: Request, auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        svc: ServicesClient = request.app.state.svc
        redis: aioredis.Redis = request.app.state.redis
        core = await svc.dashboard()
        twin = await svc.twin_status()
        stack = await _fetch_stack(svc)
        services = await probe_services()
        health_prev = await _safe_health_prev(redis)
        return {
            "ok": not core.get("error"),
            "core": core,
            "metrics": _metrics_snapshot(core),
            "models": _models_snapshot(core),
            "twin": twin,
            "stack": {k: {"ok": v, "label": _labels().get(k, k)} for k, v in stack.items()},
            "health_prev": health_prev,
            "services": services,
            "auth_via": auth.via,
            "agent_mode": core.get("agent_mode"),
            "ts": int(time.time()),
        }
