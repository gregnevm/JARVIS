"""Client-API: MCP-хаб (AP-7.4) — ре-експонує агрегатор MCP-серверів JARVIS.

Тонкий проксі до tools `/mcp/*` під єдиною client-API auth. Дозволяє вихідному конектору
(`.claude/skills/jarvis`) бути **керованим MCP-хабом**: будь-який downstream-сервер, який знає
JARVIS, доступний хосту через цей роут — з нашою auth попереду. За прапором `ENABLE_MCP_HUB`
(S2: дефолт off; вимкнено → 404). Бізнес-логіка не дублюється — gateway лише I/O (S3).

Handler-и — на рівні модуля (тестовні прямим викликом без TestClient; повний інтеграційний —
на CI, через локальний TestClient-hang). Redaction перед downstream — наступний крок AP-7.4.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jarvis_core.context import RequestContext
from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.mcp")


class McpCallBody(BaseModel):
    server: str
    tool: str
    arguments: dict[str, Any] = {}


def _require_enabled() -> None:
    if not settings.enable_mcp_hub:
        raise HTTPException(status_code=404, detail="MCP hub disabled")


async def _tools(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    # R2 «Тонкий шлюз»: увесь службовий HTTP gateway — через jarvis_core.service_client.
    return await call_dict(
        settings.tools_url, method, path, json=payload, timeout=30.0, service="tools"
    )


async def list_mcp_servers(
    ctx: RequestContext = Depends(resolve_client_context),
) -> dict[str, Any]:
    """Які downstream MCP-сервери знає JARVIS (агрегатор). Auth обов'язкова (401 інакше)."""
    _require_enabled()
    try:
        return await _tools("GET", "/mcp/servers")
    except ServiceError as exc:
        logger.warning("mcp servers proxy failed: %s", type(exc).__name__)
        return {"servers": [], "error": "tools_unreachable"}


async def call_mcp_tool(
    body: McpCallBody,
    ctx: RequestContext = Depends(resolve_client_context),
) -> dict[str, Any]:
    """Викликати tool downstream MCP-сервера з агрегатора (auth попереду, fail-fast на вході)."""
    _require_enabled()
    if not body.server.strip() or not body.tool.strip():
        raise HTTPException(status_code=400, detail="server and tool required")
    try:
        return await _tools(
            "POST", "/mcp/call",
            {"server": body.server, "tool": body.tool, "arguments": body.arguments},
        )
    except ServiceError as exc:
        logger.warning("mcp call proxy failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="tools unreachable") from exc


def register(router: APIRouter) -> None:
    router.add_api_route("/mcp/servers", list_mcp_servers, methods=["GET"])
    router.add_api_route("/mcp/call", call_mcp_tool, methods=["POST"])
