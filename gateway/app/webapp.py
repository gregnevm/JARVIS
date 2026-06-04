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

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from . import artifacts as app_artifacts
from .auth import agent_mode_denied_message
from .config import settings
from .telegram_webapp_auth import authorize_allowed

logger = logging.getLogger("jarvis.gateway.webapp")

router = APIRouter()

_INDEX = Path(__file__).parent / "static" / "app.html"


def authorize(init_data: str | None) -> int:
    """Повертає Telegram user_id або кидає 401/403. Поважає whitelist."""
    if not init_data and settings.webapp_dev_open:
        return 0
    return authorize_allowed(init_data)


class ModeBody(BaseModel):
    mode: str
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
    authorize(x_telegram_init_data)
    svc = request.app.state.svc
    dash = await svc.dashboard()
    twin = await svc.twin_status()
    return {
        "ok": not dash.get("error"),
        "core": dash,
        "twin": twin,
        "ts": int(time.time()),
    }


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
    if body.mode not in {"chat", "agent", "hybrid", "computer"}:
        raise HTTPException(status_code=400, detail="bad mode")
    res: dict[str, Any] = await request.app.state.svc.set_mode(body.mode)
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


@router.post("/app/macro/{name}")
async def app_run_macro(
    name: str,
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authorize(x_telegram_init_data)
    text = await request.app.state.tools.run_macro(user_id, name)
    return {"text": text}
