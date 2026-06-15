"""Telegram Mini App — веб-дашборд JARVIS.

Подає односторінковий апп на /app і JSON-API на /app/* для нього. Mini App
відкривається з Telegram через кнопку-меню (web_app), яку реєструємо на старті,
якщо задано PUBLIC_APP_URL (Telegram вимагає https).

Авторизація — через Telegram WebApp `initData`: клієнт надсилає підписаний рядок,
ми перевіряємо HMAC підписом від bot_token і пускаємо лише user_id з whitelist.
Для локального перегляду в браузері (без Telegram) — прапор WEBAPP_DEV_OPEN.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from . import artifacts as app_artifacts
from ._helpers import AGENT_MODES, require_mode, require_text
from .auth import agent_mode_denied_message, can_change_agent_mode
from .config import settings
from .runtime_flags import get_flags, set_flag
from .telegram_webapp_auth import authorize_allowed

logger = logging.getLogger("jarvis.gateway.webapp")

router = APIRouter()

_INDEX = Path(__file__).parent / "static" / "app.html"


def authorize(init_data: str | None) -> int:
    """Повертає Telegram user_id або кидає 401/403. Поважає whitelist."""
    if not init_data and settings.webapp_dev_open:
        return 0
    return authorize_allowed(init_data)


def _require_admin(user_id: int) -> None:
    """403 "admin only", якщо користувачу заборонено змінювати режим агента.

    Узагальнює побайтово ідентичний 2-рядковий блок `if not
    can_change_agent_mode(user_id): raise HTTPException(403, "admin
    only")`, повторений 4 рази в ендпоінтах цього модуля
    (`app_set_flag`, `app_lora_versions`, `app_lora_promote`,
    `app_lora_rollback`) — усі вимагають прав адміна на зміну режиму/LoRA."""
    if not can_change_agent_mode(user_id):
        raise HTTPException(status_code=403, detail="admin only")


class ModeBody(BaseModel):
    mode: str
    init_data: str | None = None


class FlagBody(BaseModel):
    name: str
    enabled: bool
    init_data: str | None = None


class LoraPromoteBody(BaseModel):
    version: str
    init_data: str | None = None


_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@router.get("/app", response_class=HTMLResponse)
async def app_index() -> Response:
    try:
        body = _INDEX.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="app not built") from None
    return HTMLResponse(body, headers=_NO_CACHE)


@router.get("/app/ping")
async def app_ping() -> dict[str, bool]:
    return {"ok": True}


@router.get("/app/data")
async def app_data(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data)
    svc = request.app.state.svc
    dash = await svc.dashboard()
    twin = await svc.twin_status()
    flags = await get_flags(request.app.state.redis)
    return {
        "ok": not dash.get("error"),
        "core": dash,
        "twin": twin,
        "flags": flags,
        "can_change_mode": can_change_agent_mode(user_id) if user_id else False,
        "ts": int(time.time()),
    }


@router.get("/app/sessions")
async def app_sessions(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    limit: int = 8,
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data)
    lim = max(1, min(limit, 20))
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(
                f"{settings.memory_url.rstrip('/')}/sessions",
                params={"user_id": user_id, "limit": lim},
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        logger.warning("sessions fetch failed: %s", exc)
        return {"sessions": [], "error": str(exc)}


@router.post("/app/flags")
async def app_set_flag(
    request: Request,
    body: FlagBody,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data or body.init_data)
    _require_admin(user_id)
    if body.name not in ("streaming", "voice_reply"):
        raise HTTPException(status_code=400, detail="bad flag")
    await set_flag(request.app.state.redis, body.name, body.enabled)
    flags = await get_flags(request.app.state.redis)
    return {"ok": True, "flags": flags}


@router.post("/app/mode")
async def app_set_mode(
    request: Request,
    body: ModeBody,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data or body.init_data)
    if user_id:
        denied = agent_mode_denied_message(user_id)
        if denied:
            raise HTTPException(status_code=403, detail=denied)
    mode = require_mode(body.mode, AGENT_MODES)
    res: dict[str, Any] = await request.app.state.svc.set_mode(mode)
    return res


@router.get("/app/artifact")
async def app_artifact(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    """Поточний артефакт Канвасу (останній показаний)."""
    user_id = authorize(x_telegram_init_data)
    try:
        rec = await app_artifacts.get_current(request.app.state.redis, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("artifact get failed: %s", exc)
        return {"empty": True}
    if not rec:
        return {"empty": True}
    return {"empty": False, "artifact": rec}


@router.get("/app/artifacts")
async def app_artifacts_list(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    """Історія артефактів (новіші першими) + поточний."""
    user_id = authorize(x_telegram_init_data)
    redis = request.app.state.redis
    try:
        items = await app_artifacts.list_history(redis, user_id)
        current = await app_artifacts.get_current(redis, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("artifacts list failed: %s", exc)
        return {"items": [], "current": None}
    return {"items": items, "current": current}


@router.delete("/app/artifact")
async def app_artifact_clear(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, bool]:
    user_id = authorize(x_telegram_init_data)
    try:
        await app_artifacts.clear_user(request.app.state.redis, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("artifact clear failed: %s", exc)
    return {"ok": True}


async def _remote_bundle(
    request: Request, user_id: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    tools: Any = request.app.state.tools
    dash, remote, macros = await asyncio.gather(
        request.app.state.svc.dashboard(),
        tools.remote_status(user_id),
        tools.list_macros(),
    )
    return dash, remote, macros


@router.get("/app/remote")
async def app_remote(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data)
    try:
        dash, remote, macros = await asyncio.wait_for(
            _remote_bundle(request, user_id), timeout=8.0
        )
    except asyncio.TimeoutError:
        logger.warning("app/remote timeout user=%s", user_id)
        dash = await request.app.state.svc.dashboard()
        remote, macros = {}, {"macros": []}
    return {
        "core": dash,
        "pending": remote.get("pending"),
        "audit": remote.get("audit"),
        "learned": remote.get("learned") or {},
        "macros": macros.get("macros") or [],
    }


@router.post("/app/trust")
async def app_trust(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authorize(x_telegram_init_data)
    await request.app.state.tools.grant_trust(user_id)
    return {"status": "trusted"}


@router.get("/app/twin/versions")
async def app_twin_versions(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data)
    _require_admin(user_id)
    return await request.app.state.svc.twin_lora_versions()


@router.post("/app/twin/promote")
async def app_twin_promote(
    request: Request,
    body: LoraPromoteBody,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data or body.init_data)
    _require_admin(user_id)
    version = require_text(body.version, field="version")
    return await request.app.state.svc.twin_promote_lora(version)


@router.post("/app/twin/rollback")
async def app_twin_rollback(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    n: int = 1,
) -> dict[str, Any]:
    user_id = authorize(x_telegram_init_data)
    _require_admin(user_id)
    return await request.app.state.svc.twin_rollback_lora(max(1, min(n, 5)))


@router.post("/app/macro/{name}")
async def app_run_macro(
    name: str,
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authorize(x_telegram_init_data)
    text = await request.app.state.tools.run_macro(user_id, name)
    return {"text": text}


from .webapp_ps import register_ps_routes  # noqa: E402

register_ps_routes(router)
