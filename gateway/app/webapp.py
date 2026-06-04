"""Telegram Mini App — веб-дашборд JARVIS.

Подає односторінковий апп на /app і JSON-API на /app/* для нього. Mini App
відкривається з Telegram через кнопку-меню (web_app), яку реєструємо на старті,
якщо задано PUBLIC_APP_URL (Telegram вимагає https).

Авторизація — через Telegram WebApp `initData`: клієнт надсилає підписаний рядок,
ми перевіряємо HMAC підписом від bot_token і пускаємо лише user_id з whitelist.
Для локального перегляду в браузері (без Telegram) — прапор WEBAPP_DEV_OPEN.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger("jarvis.gateway.webapp")

router = APIRouter()

_INDEX = Path(__file__).parent / "static" / "app.html"
# initData старіше за це — відхиляємо (захист від replay).
_MAX_AUTH_AGE = 24 * 3600


def _parse_init_data(init_data: str) -> dict[str, str] | None:
    if not init_data:
        return None
    try:
        return dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None


def _valid_signature(pairs: dict[str, str], bot_token: str) -> bool:
    received = pairs.get("hash", "")
    if not received:
        return False
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, received)


def authorize(init_data: str | None) -> int:
    """Повертає Telegram user_id або кидає 401/403. Поважає whitelist."""
    pairs = _parse_init_data(init_data or "")
    if pairs is None:
        if settings.webapp_dev_open:
            return 0  # dev-режим: анонімний перегляд у браузері
        raise HTTPException(status_code=401, detail="no init data")

    if not settings.telegram_bot_token or not _valid_signature(pairs, settings.telegram_bot_token):
        raise HTTPException(status_code=401, detail="bad signature")

    auth_date = pairs.get("auth_date")
    if auth_date and auth_date.isdigit() and time.time() - int(auth_date) > _MAX_AUTH_AGE:
        raise HTTPException(status_code=401, detail="init data expired")

    try:
        user = json.loads(pairs.get("user", "{}"))
        user_id = int(user.get("id"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="no user") from None

    allowed = settings.allowed_ids
    if allowed and user_id not in allowed:
        raise HTTPException(status_code=403, detail="not allowed")
    return user_id


class ModeBody(BaseModel):
    mode: str
    init_data: str | None = None


@router.get("/app", response_class=HTMLResponse)
async def app_index() -> HTMLResponse:
    try:
        return HTMLResponse(_INDEX.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="app not built") from None


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
    authorize(x_telegram_init_data or body.init_data)
    if body.mode not in {"chat", "agent", "hybrid"}:
        raise HTTPException(status_code=400, detail="bad mode")
    res: dict[str, Any] = await request.app.state.svc.set_mode(body.mode)
    return res
