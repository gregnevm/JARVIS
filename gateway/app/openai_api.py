"""P11 OpenAI-compatible API — opt-in /v1/chat/completions."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from collections.abc import Callable, Coroutine
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from .config import settings


def _err_type(status: int) -> str:
    """HTTP status → OpenAI error.type (AP-2.6)."""
    if status in (401, 403):
        return "authentication_error"
    if status == 429:
        return "rate_limit_error"
    if status == 402:
        return "insufficient_quota"
    if status >= 500:
        return "api_error"
    return "invalid_request_error"


class _OpenAIErrorRoute(APIRoute):
    """Перетворює HTTPException у тіло у форматі OpenAI: {"error": {...}} (AP-2.6).

    Скоупнуто лише на `/v1`-роутер — решта API лишається з FastAPI `{"detail": …}`."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[object, object, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={
                        "error": {
                            "message": exc.detail,
                            "type": _err_type(exc.status_code),
                            "code": None,
                        }
                    },
                )

        return handler


router = APIRouter(prefix="/v1", tags=["openai"], route_class=_OpenAIErrorRoute)


class ChatMessage(BaseModel):
    role: str
    content: str | None = ""


class ChatCompletionRequest(BaseModel):
    model: str = "jarvis"
    messages: list[ChatMessage]
    stream: bool = False
    user: str | None = None


class EmbeddingsRequest(BaseModel):
    model: str = "nomic-embed-text"
    input: str | list[str]
    user: str | None = None
    encoding_format: str | None = None  # лише 'float' підтримується; поле ігнорується


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


def _resolve_user_id(request: Request, body: ChatCompletionRequest) -> int:
    hdr = request.headers.get("x-jarvis-user-id") or request.headers.get("X-JARVIS-User-Id")
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
    default = settings.openai_default_user_id
    if default:
        return int(default)
    ids = settings.allowed_ids
    if ids:
        return next(iter(ids))
    raise HTTPException(status_code=400, detail="user_id required (X-JARVIS-User-Id header)")


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


async def _memory_embed(text: str) -> list[float]:
    """Ембединг через memory-сервіс (nomic-embed-text). Викидає httpx.HTTPError на збій."""
    url = f"{settings.memory_url.rstrip('/')}/embed"
    async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
        resp = await client.post(url, json={"text": text})
        resp.raise_for_status()
        data = resp.json()
    return [float(x) for x in (data.get("embedding") or [])]


@router.post("/embeddings")
async def embeddings(
    request: Request,
    body: EmbeddingsRequest,
    _: None = Depends(_auth_bearer),
) -> dict[str, Any]:
    """OpenAI-сумісні embeddings (AP-2.1) → nomic-embed-text у memory-сервісі."""
    raw = body.input
    inputs = [raw] if isinstance(raw, str) else list(raw)
    inputs = [str(t) for t in inputs if str(t).strip()]
    if not inputs:
        raise HTTPException(status_code=400, detail="input required")
    data: list[dict[str, Any]] = []
    for i, text in enumerate(inputs):
        try:
            vec = await _memory_embed(text)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"embedding backend error: {exc}") from exc
        data.append({"object": "embedding", "index": i, "embedding": vec})
    return {
        "object": "list",
        "data": data,
        "model": body.model or "nomic-embed-text",
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@router.get("/models")
async def list_models(request: Request, _: None = Depends(_auth_bearer)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "jarvis", "object": "model", "owned_by": "jarvis"},
            {"id": "jarvis-agent", "object": "model", "owned_by": "jarvis"},
            {"id": "nomic-embed-text", "object": "model", "owned_by": "jarvis"},
        ],
    }
