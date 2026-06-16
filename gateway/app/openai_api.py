"""P11 OpenAI-compatible API — opt-in /v1/chat/completions."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
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


def _key_store(request: Request) -> Any:
    from .saas.api_keys import ApiKeyStore

    return ApiKeyStore(request.app.state.redis)


async def _authenticate(request: Request) -> dict[str, Any]:
    """Аутентифікація `/v1` (AP-1.4): root-ключ (`OPENAI_API_KEY`) АБО керований sk-jarvis-key.

    Повертає {root, scopes, key_id}; scopes=None → усі скоупи (root)."""
    import hmac

    if not settings.enable_openai_api:
        raise HTTPException(status_code=404, detail="OpenAI API disabled")
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth[7:].strip()
    root_key = (settings.openai_api_key or "").strip()
    if root_key and hmac.compare_digest(token, root_key):
        return {"root": True, "scopes": None, "key_id": None}
    rec = await _key_store(request).verify(token)
    if rec is not None:
        return {"root": False, "scopes": set(rec.get("scopes") or []), "key_id": rec["id"]}
    raise HTTPException(status_code=401, detail="invalid api key")


def require_scope(scope: str) -> Callable[[Request], Coroutine[object, object, None]]:
    """Залежність: аутентифікує і вимагає `scope` (root має всі) — AP-1.5."""

    async def dep(request: Request) -> None:
        ctx = await _authenticate(request)
        request.state.api_auth = ctx
        scopes = ctx.get("scopes")
        if scopes is not None and scope not in scopes:
            raise HTTPException(status_code=403, detail=f"api key missing scope: {scope}")

    return dep


async def _auth_bearer(request: Request) -> None:
    """Бекворд-сумісно: будь-який валідний ключ (root або керований), без scope-обмежень."""
    await _authenticate(request)


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
    _: None = Depends(require_scope("chat")),
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


@router.get("/models")
async def list_models(request: Request, _: None = Depends(_auth_bearer)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "jarvis", "object": "model", "owned_by": "jarvis"},
            {"id": "jarvis-agent", "object": "model", "owned_by": "jarvis"},
        ],
    }
