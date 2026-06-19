"""P11 OpenAI-compatible API — opt-in /v1/chat/completions."""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger("jarvis.gateway.openai")

# AP-2.6: статус → OpenAI error.type
_ERR_TYPE = {
    401: "authentication_error",
    403: "authentication_error",
    402: "insufficient_quota",
    429: "rate_limit_error",
}

# OpenAI Model.created — обовʼязкове int-поле в SDK (інакше `client.models.list()`
# падає на валідації). Статичний epoch: моделі не «створюються» per-request (AP-2.3).
_MODEL_CREATED = 1700000000


def _validation_message(exc: RequestValidationError) -> str:
    """Стислий рядок із pydantic-помилок (`loc: msg`), без дампу складних `ctx`-обʼєктів."""
    parts = [
        f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', 'invalid')}".lstrip(": ")
        for err in exc.errors()
    ]
    return "; ".join(parts) or "invalid request"


def _openai_error_body(status: int, detail: Any) -> dict[str, Any]:
    if status >= 500:
        etype = "api_error"
    else:
        etype = _ERR_TYPE.get(status, "invalid_request_error")
    msg = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    return {"error": {"message": msg, "type": etype, "code": status}}


class _OpenAIErrorRoute(APIRoute):
    """Перетворює HTTPException у тіло помилки формату OpenAI (AP-2.6).

    Діє ЛИШЕ на `/v1` роутер — решта API лишає FastAPI `{"detail": ...}`."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            start = time.monotonic()
            status = 500
            try:
                resp = await original(request)
                status = resp.status_code
                return resp
            except RequestValidationError as exc:
                # Pydantic body/query валідація (422) — теж у OpenAI-конверті, інакше
                # офіційний openai SDK не розпарсить помилку (шукає ключ `error`).
                status = 422
                return JSONResponse(
                    status_code=422,
                    content=_openai_error_body(422, _validation_message(exc)),
                )
            except HTTPException as exc:
                status = exc.status_code
                return JSONResponse(
                    status_code=exc.status_code,
                    content=_openai_error_body(exc.status_code, exc.detail),
                    headers=getattr(exc, "headers", None),
                )
            except Exception:  # noqa: BLE001 — будь-яка неперехоплена → OpenAI 500-конверт
                # Деталі (traceback) у лог; клієнту — узагальнене, без сирого exc (no info-leak).
                logger.exception("/v1 handler crashed at %s", request.url.path)
                status = 500
                return JSONResponse(status_code=500, content=_openai_error_body(500, "internal error"))
            finally:
                try:
                    from .saas.request_log import RequestLogStore

                    ctx = getattr(request.state, "api_auth", None) or {}
                    await RequestLogStore(request.app.state.redis).record(
                        method=request.method,
                        path=request.url.path,
                        status=status,
                        ms=int((time.monotonic() - start) * 1000),
                        key_id=str(ctx.get("key_id") or "root"),
                    )
                except Exception:  # noqa: BLE001 — лог best-effort
                    pass

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
    encoding_format: str | None = None  # лише 'float' підтримується; поле ігнорується (drop-in compat #16)


class JobRequest(BaseModel):
    input: str
    mode: str = "auto"
    user: str | None = None


class ResponsesRequest(BaseModel):
    """OpenAI Responses API (агентний): input як рядок або список item'ів."""

    model: str = "jarvis-agent"
    input: str | list[dict[str, Any]]
    user: str | None = None


def _key_store(request: Request) -> Any:
    from .saas.api_keys import ApiKeyStore

    return ApiKeyStore(request.app.state.redis)


def _usage_store(request: Request) -> Any:
    from .saas.usage import UsageStore

    return UsageStore(request.app.state.redis)


async def _authenticate(request: Request) -> dict[str, Any]:
    """Аутентифікація `/v1` (AP-1.4): root-ключ (`OPENAI_API_KEY`) АБО керований sk-jarvis-key.

    Повертає {root, scopes, key_id}; scopes=None → усі скоупи (root). Веде usage (AP-2.4)."""
    import hmac

    if not settings.enable_openai_api:
        raise HTTPException(status_code=404, detail="OpenAI API disabled")
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth[7:].strip()
    root_key = (settings.openai_api_key or "").strip()
    ctx: dict[str, Any] | None = None
    if root_key and hmac.compare_digest(token, root_key):
        ctx = {"root": True, "scopes": None, "key_id": None}
    else:
        rec = await _key_store(request).verify(token)
        if rec is not None:
            ctx = {"root": False, "scopes": set(rec.get("scopes") or []), "key_id": rec["id"]}
    if ctx is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    request.state.api_auth = ctx
    if ctx.get("key_id"):  # rate-limit керовані ключі (root — без обмеження), AP-4
        await _check_rate_limit(request, str(ctx["key_id"]))
    await _usage_store(request).record(str(ctx.get("key_id") or "root"), request.url.path)
    return ctx


def _rate_limit_headers(now: int, limit: int | None = None) -> dict[str, str]:
    """Стандартні rate-limit заголовки для 429 (фіксоване хвилинне вікно `now//60`).

    Офіційний openai SDK читає `Retry-After` для експоненційного backoff — без нього
    клієнт ретраїть наосліп і per-key/per-uid ліміт не виконує DoS/cost-функції (AP-4).
    `reset` = секунди до наступного вікна (1..60). `X-RateLimit-Limit/Remaining`
    додаються лише коли cap відомий (>0).
    """
    reset_epoch = (now // 60 + 1) * 60
    headers = {"Retry-After": str(reset_epoch - now), "X-RateLimit-Reset": str(reset_epoch)}
    if limit is not None and limit > 0:
        headers["X-RateLimit-Limit"] = str(limit)
        headers["X-RateLimit-Remaining"] = "0"
    return headers


async def _check_rate_limit(request: Request, key_id: str) -> None:
    """Per-key ліміт запитів/хв (AP-4). 0 = вимкнено. Best-effort: збій Redis → пропускаємо."""
    limit = settings.openai_key_rate_limit_per_min
    if limit <= 0:
        return
    now = int(time.time())
    k = f"jarvis:ratelimit:{key_id}:{now // 60}"
    try:
        n = int(await request.app.state.redis.incr(k))
        if n == 1:
            await request.app.state.redis.expire(k, 70)
    except Exception:  # noqa: BLE001 — ліміт не має ламати запит при збої сховища
        return
    if n > limit:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded for this api key",
            headers=_rate_limit_headers(now, limit),
        )


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
    _: None = Depends(require_scope("chat")),
) -> Any:
    text = _extract_text(body.messages)
    if not text:
        raise HTTPException(status_code=400, detail="messages required")
    uid = _resolve_user_id(request, body)
    # P0-5: кожен виклик — дорогий agent-turn. Rate-limit на той самий лічильник, що
    # й Telegram-канал (DoS/cost-захист; AGENTS §A «rate-limit на ключ»).
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is not None and not await limiter.allow(uid):
        # Той самий контракт backoff-заголовків, що й per-key 429 (AP-4): кожен /v1
        # 429 несе Retry-After, інакше SDK ретраїть наосліп.
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers=_rate_limit_headers(int(time.time()), getattr(limiter, "limit", None)),
        )
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
                # Не світимо сирий exc клієнту (внутрішні шляхи/деталі) — логуємо на
                # сервері, у потік віддаємо узагальнене. Публічний /v1 = no info-leak.
                logger.warning("chat stream failed for uid=%s: %s", uid, exc)
                yield _chunk(cid, model, "\n[stream error]")
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
    """Викликає memory `/embed` (nomic-embed-text); 502 на збій бекенду (AP-2.1)."""
    url = settings.memory_url.rstrip("/") + "/embed"
    try:
        async with httpx.AsyncClient(timeout=30.0) as cli:
            resp = await cli.post(url, json={"text": text})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"embedding backend error: {exc}") from exc
    vec = data.get("embedding")
    if not isinstance(vec, list):
        raise HTTPException(status_code=502, detail="embedding backend returned no vector")
    return [float(x) for x in vec]


@router.post("/embeddings")
async def embeddings(
    request: Request,
    body: EmbeddingsRequest,
    _: None = Depends(require_scope("embeddings")),
) -> dict[str, Any]:
    """OpenAI-сумісний `/v1/embeddings` → memory `nomic-embed-text` (AP-2.1)."""
    items = [body.input] if isinstance(body.input, str) else list(body.input)
    items = [s for s in items if isinstance(s, str) and s.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="input required")
    data: list[dict[str, Any]] = []
    for i, text in enumerate(items):
        vec = await _memory_embed(text)
        data.append({"object": "embedding", "index": i, "embedding": vec})
    total = sum(len(t.split()) for t in items)
    return {
        "object": "list",
        "data": data,
        "model": body.model or "nomic-embed-text",
        "usage": {"prompt_tokens": total, "total_tokens": total},
    }


def _resolve_uid(request: Request, user: str | None = None) -> int:
    """Generic user-id resolver (header → body.user → default → перший allowed)."""
    hdr = request.headers.get("x-jarvis-user-id") or request.headers.get("X-JARVIS-User-Id")
    if hdr:
        try:
            return int(hdr.strip())
        except ValueError:
            pass
    if user:
        try:
            return int(user)
        except ValueError:
            pass
    default = settings.openai_default_user_id
    if default:
        return int(default)
    ids = settings.allowed_ids
    if ids:
        return next(iter(ids))
    raise HTTPException(status_code=400, detail="user_id required (X-JARVIS-User-Id header)")


def _job_view(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rec.get("id"),
        "object": "job",
        "status": rec.get("status", "unknown"),
        "created_at": rec.get("created_at"),
        "result": rec.get("result") or rec.get("output"),
        "mode": rec.get("mode") or rec.get("kind"),
    }


@router.post("/jobs")
async def create_job(
    request: Request,
    body: JobRequest,
    _: None = Depends(require_scope("jobs")),
) -> dict[str, Any]:
    """Async-задача (AP-2.5): research/team/coding через bg_jobs — повертає job id."""
    text = (body.input or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="input required")
    uid = _resolve_uid(request, body.user)
    rec = await request.app.state.tools.create_bg_job(uid, text, (body.mode or "auto").strip())
    if rec.get("error"):
        raise HTTPException(status_code=502, detail=str(rec["error"]))
    return _job_view(rec)


@router.get("/jobs/{job_id}")
async def get_job(
    request: Request,
    job_id: str,
    _: None = Depends(require_scope("jobs")),
) -> dict[str, Any]:
    """Статус async-задачі (AP-2.5)."""
    uid = _resolve_uid(request)
    rec = await request.app.state.tools.get_bg_job(job_id, uid)
    if rec is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_view(rec)


def _responses_input_text(value: str | list[dict[str, Any]]) -> str:
    """Витягує текст із Responses `input` (рядок або список item'ів)."""
    if isinstance(value, str):
        return value.strip()
    last = ""
    for item in value:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            text = content.strip()
        elif isinstance(content, list):
            parts = [
                str(c.get("text", "")).strip()
                for c in content
                if isinstance(c, dict) and c.get("text")
            ]
            text = " ".join(p for p in parts if p)
        else:
            text = ""
        if text:
            if item.get("role") == "user":
                last = text
            elif not last:
                last = text
    return last


@router.post("/responses")
async def responses(
    request: Request,
    body: ResponsesRequest,
    _: None = Depends(require_scope("chat")),
) -> dict[str, Any]:
    """Агентний `/v1/responses` (AP-2.2) — мапа на агент-луп (mode=agent, tool-use)."""
    text = _responses_input_text(body.input)
    if not text:
        raise HTTPException(status_code=400, detail="input required")
    uid = _resolve_uid(request, body.user)
    result = await request.app.state.tools.process({"user_id": uid, "text": text, "mode": "agent"})
    rid = f"resp_{uuid.uuid4().hex[:24]}"
    return {
        "id": rid,
        "object": "response",
        "created_at": int(time.time()),
        "model": body.model or "jarvis-agent",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result, "annotations": []}],
            }
        ],
        "output_text": result,
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


@router.get("/usage")
async def usage(request: Request, days: int = 7, _: None = Depends(_auth_bearer)) -> dict[str, Any]:
    """Per-key usage за період (AP-2.4) — лічильники запитів для ключа-викликача."""
    ctx = getattr(request.state, "api_auth", None) or {}
    kid = str(ctx.get("key_id") or "root")
    return await _usage_store(request).summary(kid, days=days)


async def _ollama_catalog(request: Request) -> list[dict[str, Any]]:
    """Реальний каталог моделей із Ollama (AP-2.3), best-effort — порожньо при збої."""
    try:
        core = await request.app.state.svc.dashboard()
        host = str(core.get("ollama_host") or "")
        if not host:
            return []
        from .platform.models import _ollama_tags

        out: list[dict[str, Any]] = []
        for m in await _ollama_tags(host):
            name = m.get("name")
            if name:
                out.append({"id": str(name), "object": "model", "created": _MODEL_CREATED, "owned_by": "ollama"})
        return out
    except Exception:  # noqa: BLE001 — каталог не має ламати ендпоінт
        return []


@router.get("/models")
async def list_models(request: Request, _: None = Depends(_auth_bearer)) -> dict[str, Any]:
    data: list[dict[str, Any]] = [
        {"id": "jarvis", "object": "model", "created": _MODEL_CREATED, "owned_by": "jarvis"},
        {"id": "jarvis-agent", "object": "model", "created": _MODEL_CREATED, "owned_by": "jarvis"},
        {"id": "nomic-embed-text", "object": "model", "created": _MODEL_CREATED, "owned_by": "jarvis"},
    ]
    seen = {m["id"] for m in data}
    for m in await _ollama_catalog(request):  # AP-2.3: реальний каталог
        if m["id"] not in seen:
            data.append(m)
            seen.add(m["id"])
    return {"object": "list", "data": data}
