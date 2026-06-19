"""Client-API `/api/v1/*` — стабільний версіонований контракт для всіх клієнтів (CL-1.3).

Seed-набір: JWT-логін (CL-1.1) + єдиний whoami через unified resolver (CL-1.4). Доповнюється
поетапно (chat/sessions/projects), консолідуючи `/app/*` і `/platform/api/*` без big-bang.
OpenAPI під tag `client-api` (CL-1.5) — для генерації mobile-клієнта з `/openapi.json`.
"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import DEFAULT_ORG_ID, RequestContext, redis_key
from jarvis_core.plan_limits import public_limits

from ..config import settings
from ..platform.auth import primary_admin_id, verify_admin_password
from ..saas import auth as jwt_auth
from . import apps as apps_api
from . import chat as chat_api
from . import chrome as chrome_api
from . import code as code_api
from . import confirm as confirm_api
from . import driver as driver_api
from . import context as context_api
from . import workspace as workspace_api
from .deps import resolve_client_context

router = APIRouter(prefix="/api/v1", tags=["client-api"])


class LoginBody(BaseModel):
    username: str = "admin"
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class PairBody(BaseModel):
    token: str


class TgPollBody(BaseModel):
    token: str


@router.post("/auth/login")
async def login(body: LoginBody) -> dict[str, Any]:
    """Self-hosted admin-логін (PLATFORM_PASSWORD) → пара JWT. Multi-user signup → SAAS PR#6."""
    if not jwt_auth.jwt_enabled():
        raise HTTPException(status_code=503, detail="JWT auth disabled (set JWT_SECRET)")
    if not verify_admin_password(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return jwt_auth.issue_tokens(primary_admin_id())


@router.post("/auth/refresh")
async def refresh(body: RefreshBody) -> dict[str, Any]:
    if not jwt_auth.jwt_enabled():
        raise HTTPException(status_code=503, detail="JWT auth disabled (set JWT_SECRET)")
    try:
        claims = jwt_auth.decode(body.refresh_token, expect="refresh")
        uid = int(claims["sub"])
    except (jwt_auth.JWTError, KeyError, ValueError, TypeError) as exc:
        # будь-який малформ підписаного токена → чистий 401 (не 500/stack-trace)
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    # role/plan НЕ беремо з refresh-токена: він їх не несе й не авторитетний по них.
    # Self-hosted → канонічні owner/studio (як у login); multi-user → з БД (PR#6).
    # Інакше прострочений токен зі старою роллю міг би «заморозити» привілеї.
    access = jwt_auth.issue_access(uid, org_id=claims.get("org"))
    return {"access_token": access, "token_type": "bearer", "expires_in": settings.jwt_access_ttl}


@router.post("/auth/pair")
async def auth_pair(body: PairBody, request: Request) -> dict[str, Any]:
    """Обмін one-time пейринг-токена (з `/platform/api/apk/pair`) на JWT-пару.

    APK сканує QR → deeplink дає token → цей ендпоінт. Токен одноразовий (видаляємо)."""
    if not jwt_auth.jwt_enabled():
        raise HTTPException(status_code=503, detail="JWT auth disabled (set JWT_SECRET)")
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    redis = request.app.state.redis
    key = redis_key(DEFAULT_ORG_ID, "apk", "pair", token)
    uid = await redis.get(key)
    if not uid:
        raise HTTPException(status_code=401, detail="invalid or expired pairing token")
    await redis.delete(key)  # one-time
    try:
        return jwt_auth.issue_tokens(int(uid))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="invalid pairing token") from exc


@router.post("/auth/telegram/start")
async def tg_start(request: Request) -> dict[str, Any]:
    """Telegram-логін (крок 1): створює pending-токен → deeplink t.me/<bot>?start=tgauth_<token>."""
    if not jwt_auth.jwt_enabled():
        raise HTTPException(status_code=503, detail="JWT auth disabled (set JWT_SECRET)")
    token = secrets.token_urlsafe(18)
    await request.app.state.redis.setex(f"tgauth:{token}", 300, "pending")
    username = ""
    try:
        me = await request.app.state.tg.get_me()
        username = str(me.get("username") or "")
    except Exception:  # noqa: BLE001 — getMe не критичний, віддамо токен без deeplink
        username = ""
    deeplink = f"https://t.me/{username}?start=tgauth_{token}" if username else ""
    return {"token": token, "bot_username": username, "deeplink": deeplink, "expires_in": 300}


@router.post("/auth/telegram/poll")
async def tg_poll(body: TgPollBody, request: Request) -> dict[str, Any]:
    """Telegram-логін (крок 2): polling. pending → чекай; ok → JWT-пара; expired → почни заново."""
    if not jwt_auth.jwt_enabled():
        raise HTTPException(status_code=503, detail="JWT auth disabled (set JWT_SECRET)")
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    val = await request.app.state.redis.get(f"tgauth:{token}")
    if not val:
        return {"status": "expired"}
    if val == "pending":
        return {"status": "pending"}
    await request.app.state.redis.delete(f"tgauth:{token}")  # one-time
    try:
        tokens = jwt_auth.issue_tokens(int(val))
    except (ValueError, TypeError):
        return {"status": "expired"}
    return {"status": "ok", **tokens}


@router.post("/voice")
async def voice(
    request: Request, ctx: RequestContext = Depends(resolve_client_context)
) -> dict[str, Any]:
    """C2: нативний голос — сирий аудіо-байт-стрім → STT (whisper) → агент → відповідь."""
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty audio body")
    transcript = (await request.app.state.stt.transcribe(audio, filename="voice.m4a")).strip()
    reply = ""
    if transcript:
        uid = ctx.legacy_uid if ctx.legacy_uid is not None else int(ctx.user_id)
        reply = await request.app.state.tools.process(
            {"user_id": uid, "text": transcript, "mode": "auto"}
        )
    return {"transcript": transcript, "reply": reply}


@router.get("/whoami")
async def whoami(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
    """Єдиний identity-ендпоінт для всіх клієнтів (JWT / initData / Basic) — CL-1.4."""
    return {
        "org_id": ctx.org_id,
        "user_id": ctx.user_id,
        "role": ctx.role,
        "plan": ctx.plan,
        "limits": public_limits(ctx.plan),  # стелі плану (UNLIMITED→null) — AP-4.3
        "legacy_uid": ctx.legacy_uid,
        "via": ctx.via,
    }


# Chat — ядрова операція (CL-3.3 backend); reuse агент-шляху, без Telegram-coupling (S3).
chat_api.register(router)
# Context ingest/ретрив (CL-3, культура P9/P10) — окремий модуль, композиція (P4).
context_api.register(router)
# Computer-confirm міст для mobile (BE5, CL-3.5) — апрув дій агента з телефона.
confirm_api.register(router)
# Chats (sessions/history) + projects CRUD — тонкий проксі до memory.
workspace_api.register(router)
# APK-apps — server-updatable web-бандли для WebView застосунку.
apps_api.register(router)
# Driver — remote PC control (computer-use) з copilot.
driver_api.register(router)
# Chrome use — двосторонній контроль браузера через extension-ендпоінт.
chrome_api.register(router)
# Code — dispatch задач кодування (рідний агент; Claude-міст опційно).
code_api.register(router)
