"""PowerShell Panel API — /app/ps/* для AI Driven Computer Use Mini App."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ._helpers import require_text
from .auth import computer_denied_message
from .computer_resume import resume_text as _resume_text
from .webapp import authorize

logger = logging.getLogger("jarvis.gateway.webapp.ps")

_PS_PANEL_HINT = (
    "Користувач у PowerShell Panel Mini App. "
    "Використовуй tier T0 run_powershell для OS-задач. "
    "ЗАВЖДИ передавай as_admin: true у run_powershell (elevated PowerShell). "
    "Не використовуй GUI-клік (screen_click/uia), якщо є PS-шлях. "
    "PowerShell без | && || — для процесів достатньо Get-Process або Get-Process -Name foo,bar. "
    "Coding-задачі в репо — tool cursor_task (краще за PS/CLI). "
    "CLI fallback: run_cli python + O:\\JARVIS\\scripts\\cursor_run_task.py --task ... --cwd O:\\JARVIS. "
    "Коротко поясни що робиш.\n\n"
)


class PsAskBody(BaseModel):
    text: str
    init_data: str | None = None


class PsConfirmBody(BaseModel):
    code: str
    init_data: str | None = None


class PsResumeBody(BaseModel):
    result: str
    origin: str = ""
    init_data: str | None = None


def _ndjson_sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _check_computer_access(user_id: int) -> None:
    """403, якщо Computer Use заборонено цьому користувачу.

    `user_id == 0` означає dev-режим (немає реального Telegram-користувача
    — `WEBAPP_DEV_OPEN`) — пропускаємо перевірку, бо `computer_denied_message`
    очікує справжній user_id. Узагальнює побайтово ідентичний 4-рядковий блок
    `if user_id: denied = computer_denied_message(user_id); if denied: raise
    HTTPException(403, denied)`, повторений 5 разів у цьому файлі (ask/pending/
    confirm/cancel/resume). Не використовує `platform/workbench.py::_check_computer`
    — там завжди справжній auth.user_id (PlatformAuth), без dev-режиму, тож
    `if user_id:`-гард там не потрібен і об'єднання дало б зайву гілку для
    чужого сценарію."""
    if user_id:
        denied = computer_denied_message(user_id)
        if denied:
            raise HTTPException(status_code=403, detail=denied)


def register_ps_routes(router: APIRouter) -> None:
    @router.post("/app/ps/ask")
    async def app_ps_ask(
        request: Request,
        body: PsAskBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> StreamingResponse:
        user_id = authorize(x_telegram_init_data or body.init_data)
        _check_computer_access(user_id)
        text = require_text(body.text)
        tools = request.app.state.tools
        prompt = _PS_PANEL_HINT + text

        async def gen() -> AsyncIterator[str]:
            try:
                async for ev in tools.stream(
                    {"user_id": user_id, "text": prompt, "mode": "computer"}
                ):
                    yield _ndjson_sse(ev)
            except Exception as exc:  # noqa: BLE001
                logger.exception("ps ask stream failed")
                yield _ndjson_sse(
                    {
                        "done": True,
                        "mode": "error",
                        "iters": 0,
                        "text": f"Помилка стріму: {exc}",
                    }
                )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/app/ps/pending")
    async def app_ps_pending(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user_id = authorize(x_telegram_init_data)
        _check_computer_access(user_id)
        return await request.app.state.tools.get_ps_pending(user_id)

    @router.post("/app/ps/confirm")
    async def app_ps_confirm(
        request: Request,
        body: PsConfirmBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authorize(x_telegram_init_data or body.init_data)
        _check_computer_access(user_id)
        code = require_text(body.code, field="code")
        result, origin = await request.app.state.tools.confirm_computer(user_id, code)
        return {"result": result, "origin": origin}

    @router.post("/app/ps/cancel")
    async def app_ps_cancel(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authorize(x_telegram_init_data)
        _check_computer_access(user_id)
        await request.app.state.tools.cancel_computer(user_id)
        return {"status": "cancelled"}

    @router.post("/app/ps/resume")
    async def app_ps_resume(
        request: Request,
        body: PsResumeBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> StreamingResponse:
        user_id = authorize(x_telegram_init_data or body.init_data)
        _check_computer_access(user_id)
        result = require_text(body.result, field="result")
        tools = request.app.state.tools
        resume_text = _resume_text(body.origin, result)

        async def gen() -> AsyncIterator[str]:
            try:
                async for ev in tools.stream(
                    {"user_id": user_id, "text": resume_text, "mode": "computer"}
                ):
                    yield _ndjson_sse(ev)
            except Exception as exc:  # noqa: BLE001
                logger.exception("ps resume stream failed")
                yield _ndjson_sse(
                    {
                        "done": True,
                        "mode": "error",
                        "iters": 0,
                        "text": f"Помилка resume: {exc}",
                    }
                )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/app/ps/audit")
    async def app_ps_audit(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
        limit: int = 30,
    ) -> dict[str, Any]:
        authorize(x_telegram_init_data)
        lim = max(1, min(limit, 100))
        return await request.app.state.tools.get_ps_audit(limit=lim)

    @router.get("/app/ps/policy")
    async def app_ps_policy(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize(x_telegram_init_data)
        return await request.app.state.tools.get_ps_policy()

    @router.get("/app/ps/status")
    async def app_ps_status(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, Any]:
        user_id = authorize(x_telegram_init_data)
        svc = request.app.state.svc
        tools = request.app.state.tools
        dash, policy, trust = await svc.dashboard(), await tools.get_ps_policy(), await tools.get_trust_status(user_id)
        return {
            "hostagent_up": bool(policy.get("hostagent_up") or dash.get("hostagent_up")),
            "enable_computer_use": bool(
                policy.get("enable_computer_use") or dash.get("enable_computer_use")
            ),
            "trusted": trust.get("trusted", False),
            "trust_ttl_seconds": trust.get("ttl_seconds", 0),
            "ollama_up": bool(dash.get("ollama_up")),
        }
