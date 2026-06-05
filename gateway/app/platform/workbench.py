"""P0.3 Workbench — браузерний REPL до агента через SSE.

Прокидає `tools.stream(...)` як Server-Sent Events; UI малює tool-trace (tool_start/
tool_done), токени (delta) і фінал (done). Паритет із Telegram-стрімом — той самий
event-контракт (tools/app/agent.py:run_stream).
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.workbench")

_MODES = {"auto", "chat", "agent", "hybrid", "computer"}


class AskBody(BaseModel):
    text: str
    mode: str = "auto"


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def register(router: APIRouter) -> None:
    @router.post("/platform/api/workbench/ask")
    async def workbench_ask(
        request: Request,
        body: AskBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> StreamingResponse:
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        mode = (body.mode or "auto").strip().lower()
        if mode not in _MODES:
            raise HTTPException(status_code=400, detail="bad mode")
        tools = request.app.state.tools
        payload: dict[str, Any] = {"user_id": auth.user_id, "text": text, "mode": mode}

        async def gen() -> AsyncIterator[str]:
            try:
                async for ev in tools.stream(payload):
                    yield _sse(ev)
            except Exception as exc:  # noqa: BLE001
                logger.exception("workbench stream failed")
                yield _sse(
                    {"done": True, "mode": "error", "iters": 0, "text": f"Помилка стріму: {exc}"}
                )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
