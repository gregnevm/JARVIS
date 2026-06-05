"""PowerShell Panel API — /app/ps/* для AI Driven Computer Use Mini App."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import computer_denied_message
from .webapp import authorize

logger = logging.getLogger("jarvis.gateway.webapp.ps")

_PS_PANEL_HINT = (
    "Користувач у PowerShell Panel Mini App. "
    "Використовуй tier T0 run_powershell для OS-задач. "
    "ЗАВЖДИ передавай as_admin: true у run_powershell (elevated PowerShell). "
    "Не використовуй GUI-клік (screen_click/uia), якщо є PS-шлях. "
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


def _resume_text(origin: str, result: str) -> str:
    parts: list[str] = []
    origin = (origin or "").strip()
    if origin:
        parts.append(f"Оригінальний запит користувача:\n{origin[:3000]}")
    parts.append(f"Результат підтвердженої Computer Use дії на хості:\n{result[:6000]}")
    parts.append(
        "Коротко підсумуй для користувача українською. "
        "Якщо початкове завдання ще не виконано — продовж наступним кроком."
    )
    return "\n\n".join(parts)


def _ndjson_sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def register_ps_routes(router: APIRouter) -> None:
    @router.post("/app/ps/ask")
    async def app_ps_ask(
        request: Request,
        body: PsAskBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> StreamingResponse:
        user_id = authorize(x_telegram_init_data or body.init_data)
        if user_id:
            denied = computer_denied_message(user_id)
            if denied:
                raise HTTPException(status_code=403, detail=denied)
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
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
        if user_id:
            denied = computer_denied_message(user_id)
            if denied:
                raise HTTPException(status_code=403, detail=denied)
        return await request.app.state.tools.get_ps_pending(user_id)

    @router.post("/app/ps/confirm")
    async def app_ps_confirm(
        request: Request,
        body: PsConfirmBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authorize(x_telegram_init_data or body.init_data)
        if user_id:
            denied = computer_denied_message(user_id)
            if denied:
                raise HTTPException(status_code=403, detail=denied)
        code = (body.code or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="code required")
        result, origin = await request.app.state.tools.confirm_computer(user_id, code)
        return {"result": result, "origin": origin}

    @router.post("/app/ps/cancel")
    async def app_ps_cancel(
        request: Request,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authorize(x_telegram_init_data)
        if user_id:
            denied = computer_denied_message(user_id)
            if denied:
                raise HTTPException(status_code=403, detail=denied)
        await request.app.state.tools.cancel_computer(user_id)
        return {"status": "cancelled"}

    @router.post("/app/ps/resume")
    async def app_ps_resume(
        request: Request,
        body: PsResumeBody,
        x_telegram_init_data: str | None = Header(default=None),
    ) -> StreamingResponse:
        user_id = authorize(x_telegram_init_data or body.init_data)
        if user_id:
            denied = computer_denied_message(user_id)
            if denied:
                raise HTTPException(status_code=403, detail=denied)
        result = (body.result or "").strip()
        if not result:
            raise HTTPException(status_code=400, detail="result required")
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
