"""Client-API chat — ядрова операція `/api/v1` (CL-3.3 backend; завершує CL-1.3 контракт).

Тонкий шар: unified resolver → `RequestContext` → reuse наявного агент-шляху
(`ToolsClient.process` — той самий, що Telegram-router), без дублювання бізнес-логіки (S3).
Канал-агностично: жодного Telegram-coupling (на відміну від `run_agent_turn`, що доставляє в чат).
Споживачі: нативний mobile-клієнт (CL-3) і web SPA (CL-2); WebView-MVP поки ходить у `/app`.

Streaming (`/chat/stream` SSE) і `/sessions` (історія) — наступний крок, коли клієнт їх потребуватиме.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from .._helpers import AGENT_MODES_AUTO, require_mode, require_text
from ..agent_payload import build_agent_payload
from .deps import resolve_client_context


class ChatBody(BaseModel):
    text: str
    mode: str = "auto"


def _resolve_uid(ctx: RequestContext) -> int:
    """Числовий agent-uid (для RAG/пам'яті). Self-hosted: legacy_uid або user_id."""
    if ctx.legacy_uid is not None:
        return ctx.legacy_uid
    try:
        return int(ctx.user_id)
    except (ValueError, TypeError) as exc:
        # SaaS UUID-користувач без legacy-маппінгу — chat-міст постане в PR#4/PR#6
        raise HTTPException(status_code=503, detail="chat requires a numeric user id") from exc


def register(router: APIRouter) -> None:
    @router.post("/chat")
    async def chat(
        body: ChatBody,
        request: Request,
        ctx: RequestContext = Depends(resolve_client_context),
    ) -> dict[str, Any]:
        """Один хід агента для будь-якого клієнта (JWT/initData/Basic) → JSON-відповідь."""
        text = require_text(body.text)
        uid = _resolve_uid(ctx)
        # Fail-fast (P2): валідуємо mode на вході, як кожен сусідній agent-entry
        # (workbench/admin_panel/settings_api/webapp через require_mode SSOT),
        # а не передаємо «сире» значення downstream у tools.process.
        mode = require_mode(body.mode or "auto", AGENT_MODES_AUTO)
        payload = build_agent_payload(user_id=uid, chat_id=uid, text=text, source="api", mode=mode)
        reply = await request.app.state.tools.process(payload)
        return {"reply": reply, "mode": mode, "via": ctx.via}
