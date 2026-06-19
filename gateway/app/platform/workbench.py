"""P0.3 Workbench — браузерний REPL до агента через SSE + Computer confirm flow."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import computer_denied_message
from ..computer_resume import resume_text
from .._helpers import AGENT_MODES_AUTO, require_mode, require_text
from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.workbench")


class AskBody(BaseModel):
    text: str
    mode: str = "auto"


class ConfirmBody(BaseModel):
    code: str


class ResumeBody(BaseModel):
    result: str
    origin: str = ""
    mode: str = "computer"


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _check_computer(user_id: int) -> None:
    denied = computer_denied_message(user_id)
    if denied:
        raise HTTPException(status_code=403, detail=denied)


def register(router: APIRouter) -> None:
    @router.post("/platform/api/workbench/ask")
    async def workbench_ask(
        request: Request,
        body: AskBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> StreamingResponse:
        text = require_text(body.text)
        mode = require_mode(body.mode or "auto", AGENT_MODES_AUTO)
        if mode == "computer":
            _check_computer(auth.user_id)
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

    @router.get("/platform/api/workbench/pending")
    async def workbench_pending(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        _check_computer(auth.user_id)
        return await request.app.state.tools.get_ps_pending(auth.user_id)

    @router.post("/platform/api/workbench/confirm")
    async def workbench_confirm(
        request: Request,
        body: ConfirmBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, str]:
        _check_computer(auth.user_id)
        code = require_text(body.code, field="code")
        result, origin = await request.app.state.tools.confirm_computer(auth.user_id, code)
        return {"result": result, "origin": origin}

    @router.post("/platform/api/workbench/cancel")
    async def workbench_cancel(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, str]:
        _check_computer(auth.user_id)
        await request.app.state.tools.cancel_computer(auth.user_id)
        return {"status": "cancelled"}

    @router.post("/platform/api/workbench/resume")
    async def workbench_resume(
        request: Request,
        body: ResumeBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> StreamingResponse:
        _check_computer(auth.user_id)
        result = require_text(body.result, field="result")
        mode = require_mode(body.mode or "computer", AGENT_MODES_AUTO)
        tools = request.app.state.tools
        prompt = resume_text(body.origin, result)

        async def gen() -> AsyncIterator[str]:
            try:
                async for ev in tools.stream(
                    {"user_id": auth.user_id, "text": prompt, "mode": mode}
                ):
                    yield _sse(ev)
            except Exception as exc:  # noqa: BLE001
                logger.exception("workbench resume failed")
                yield _sse(
                    {"done": True, "mode": "error", "iters": 0, "text": f"Помилка resume: {exc}"}
                )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
