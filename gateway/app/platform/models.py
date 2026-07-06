"""P0.8 Models — Ollama tags, CHAT/AGENT/vision/embed mapping, LoRA registry.

Read-only огляд + promote/rollback LoRA для адміна (через Twin registry, як
`/app/twin/*`). Tags тягнемо з ollama_host, що повертає dashboard.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from jarvis_core.service_client import ServiceError, call

from .._helpers import require_text
from ..services import ServicesClient
from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.models")


class PromoteBody(BaseModel):
    version: str


async def _ollama_tags(host: str) -> list[dict[str, Any]]:
    host = (host or "").strip().rstrip("/")
    if not host or host == "—":
        return []
    try:
        data = await call(host, "GET", "/api/tags", timeout=5.0, service="ollama")
    except ServiceError as exc:
        logger.debug("ollama tags failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for m in data.get("models") or []:
        if not isinstance(m, dict):
            continue
        out.append(
            {
                "name": m.get("name"),
                "size": m.get("size"),
                "family": (m.get("details") or {}).get("family"),
                "param_size": (m.get("details") or {}).get("parameter_size"),
                "quant": (m.get("details") or {}).get("quantization_level"),
            }
        )
    return out


def register(router: APIRouter) -> None:
    @router.get("/platform/api/models")
    async def models_get(
        request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        svc: ServicesClient = request.app.state.svc
        core = await svc.dashboard()
        twin = await svc.twin_status()
        tags = await _ollama_tags(str(core.get("ollama_host") or ""))
        return {
            "ollama_host": core.get("ollama_host") or "—",
            "ollama_up": bool(core.get("ollama_up")),
            "mapping": {
                "chat": core.get("chat_model"),
                "agent": core.get("agent_model"),
                "vision": core.get("vision_model") or "—",
                "embed": core.get("embed_model") or "—",
            },
            "tags": tags,
            "twin": twin,
        }

    @router.get("/platform/api/models/lora")
    async def models_lora(
        request: Request, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await request.app.state.svc.twin_lora_versions()

    @router.post("/platform/api/models/lora/promote")
    async def models_lora_promote(
        body: PromoteBody,
        request: Request,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        version = require_text(body.version, field="version")
        return await request.app.state.svc.twin_promote_lora(version)

    @router.post("/platform/api/models/lora/rollback")
    async def models_lora_rollback(
        request: Request,
        _auth: PlatformAuth = Depends(require_platform_auth),
        n: int = 1,
    ) -> dict[str, Any]:
        return await request.app.state.svc.twin_rollback_lora(max(1, min(n, 5)))
