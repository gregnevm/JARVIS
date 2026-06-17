"""P11 OpenAI-compatible API — opt-in /v1/chat/completions."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import settings

router = APIRouter(prefix="/v1", tags=["openai"])


class ChatMessage(BaseModel):
    role: str
    content: str | None = ""


class ChatCompletionRequest(BaseModel):
    model: str = "jarvis"
    messages: list[ChatMessage]
    stream: bool = False
    user: str | None = None


def _auth_bearer(request: Request) -> None:
    if not settings.enable_openai_api:
        raise HTTPException(status_code=404, detail="OpenAI API disabled")
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth[7:].strip()
    if token != key:
        raise HTTPException(status_code=401, detail="invalid api key")


def _requested_uid(request: Request, body: ChatCompletionRequest) -> int | None:
    """uid, який попросив caller (header має пріоритет над body.user). None якщо немає."""
    hdr = request.headers.get("x-jarvis-user-id")  # Starlette headers — case-insensitive
    if hdr:
        try:
            return int(hdr.strip())
        except ValueError:
            pass
    if body.user:
        try:
            return int(body.user)
        except ValueError:
            pass
    return None


def _resolve_user_id(request: Request, body: ChatCompletionRequest) -> int:
    """uid для прогону агента під одним глобальним `/v1`-ключем.

    P0-4 (anti-impersonation): caller-supplied uid (header/body) приймаємо ЛИШЕ якщо
    він у `allowed_ids`. Інакше тримач єдиного OPENAI_API_KEY міг би передати
    `X-JARVIS-User-Id: <будь-хто>` і читати чужу памʼять/контекст. Невідомий uid →
    ігноруємо й падаємо на OPENAI_DEFAULT_USER_ID."""
    allowed = settings.allowed_ids
    requested = _requested_uid(request, body)
    if requested is not None and requested in allowed:
        return requested
    default = settings.openai_default_user_id
    if default:
        return int(default)
    if allowed:
        return next(iter(allowed))
    raise HTTPException(
        status_code=400, detail="user_id not resolvable (configure OPENAI_DEFAULT_USER_ID)"
    )


def _extract_text(messages: list[ChatMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        if m.role == "user" and (m.content or "").strip():
            parts.append((m.content or "").strip())
    if parts:
        return parts[-1]
    for m in reversed(messages):
        if (m.content or "").strip():
            return (m.content or "").strip()
    return ""


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _chunk(id_: str, model: str, delta: str, finish: bool = False) -> str:
    obj: dict[str, Any] = {
        "id": id_,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {} if finish else {"content": delta},
                "finish_reason": "stop" if finish else None,
            }
        ],
    }
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    _: None = Depends(_auth_bearer),
) -> Any:
    text = _extract_text(body.messages)
    if not text:
        raise HTTPException(status_code=400, detail="messages required")
    uid = _resolve_user_id(request, body)
    # P0-5: кожен виклик — дорогий agent-turn. Rate-limit на той самий лічильник, що
    # й Telegram-канал (DoS/cost-захист; AGENTS §A «rate-limit на ключ»).
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is not None and not await limiter.allow(uid):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    tools = request.app.state.tools
    cid = _completion_id()
    model = body.model or "jarvis"

    if body.stream:

        async def gen() -> AsyncIterator[str]:
            parts: list[str] = []
            try:
                async for ev in tools.stream({"user_id": uid, "text": text, "mode": "auto"}):
                    if ev.get("delta"):
                        d = str(ev["delta"])
                        parts.append(d)
                        yield _chunk(cid, model, d)
                    if ev.get("done"):
                        break
                yield _chunk(cid, model, "", finish=True)
                yield "data: [DONE]\n\n"
            except Exception as exc:  # noqa: BLE001
                yield _chunk(cid, model, f"\n[error: {exc}]")
                yield _chunk(cid, model, "", finish=True)
                yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    result = await tools.process({"user_id": uid, "text": text, "mode": "auto"})
    return {
        "id": cid,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@router.get("/models")
async def list_models(request: Request, _: None = Depends(_auth_bearer)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "jarvis", "object": "model", "owned_by": "jarvis"},
            {"id": "jarvis-agent", "object": "model", "owned_by": "jarvis"},
        ],
    }
