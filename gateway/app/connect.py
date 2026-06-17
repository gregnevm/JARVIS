"""`/connect/<token>` — Telegram one-tap → авторизована веб-сесія.

Бот мінтить connect-токен (`auth_links.mint`, прив'язаний до Telegram user_id) і дає
користувачу посилання. Один тап → браузер відкриває цей ендпоінт, ми обмінюємо токен
на JWT, кладемо його в HttpOnly-cookie і редіректимо в консоль (`/platform`). Жодного
пароля, жодного копіювання — довіра «успадковується» з Telegram.

`?format=json` → віддаємо JWT-пару як JSON (для розширення/CLI, яким потрібен сам токен,
а не cookie+redirect). `?next=/app` → куди редіректити після входу (whitelist префіксів).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import auth_links
from .auth import is_allowed
from .config import settings
from .saas import auth as jwt_auth

logger = logging.getLogger("jarvis.gateway.connect")

router = APIRouter()

# Куди дозволено редіректити після входу (захист від open-redirect).
_SAFE_NEXT = ("/platform", "/app", "/admin")


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>JARVIS · {title}</title>"
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "background:#0d1117;color:#e6edf3;display:flex;min-height:100vh;margin:0;"
        "align-items:center;justify-content:center;text-align:center}"
        ".card{max-width:420px;padding:32px;background:#161b22;border:1px solid #30363d;"
        "border-radius:16px}h1{font-size:20px;margin:0 0 12px}p{color:#8b949e;line-height:1.5}"
        "a{color:#58a6ff}code{background:#0d1117;padding:2px 6px;border-radius:6px}</style>"
        f"<div class='card'><h1>{title}</h1>{body}</div>"
    )
    return HTMLResponse(html, status_code=status)


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https" or request.url.scheme == "https"


def set_jwt_cookie(response: Response, access_token: str, request: Request) -> None:
    """Кладе access-JWT у HttpOnly-cookie (Lax) — браузер шле його з кожним запитом."""
    response.set_cookie(
        jwt_auth.JWT_COOKIE,
        access_token,
        max_age=settings.jwt_access_ttl,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )


def _safe_next(next_url: str | None) -> str:
    if next_url and any(next_url.startswith(p) for p in _SAFE_NEXT):
        return next_url
    return "/platform"


@router.get("/connect/{token}")
async def connect(
    token: str,
    request: Request,
    format: str = Query(default="html"),
    next: str | None = Query(default=None),
) -> Response:
    """Обмінює one-time connect-токен на JWT-cookie і редіректить у консоль."""
    redis = request.app.state.redis
    info = await auth_links.redeem(redis, token)
    if info is None:
        return _page(
            "Посилання недійсне",
            "<p>Лінк прострочений або вже використаний.<br>"
            "Відкрий бота в Telegram і надішли <code>/connect</code> ще раз.</p>",
            status=401,
        )
    uid, _target = info
    if not is_allowed(uid):
        return _page("Доступ заборонено", "<p>Цей акаунт не у whitelist.</p>", status=403)
    if not jwt_auth.jwt_enabled():
        return _page(
            "JWT вимкнено",
            "<p>Веб-вхід через Telegram потребує <code>JWT_SECRET</code> на сервері.<br>"
            "Задай його у <code>.env</code> і перезапусти gateway.</p>",
            status=503,
        )
    tokens = jwt_auth.issue_tokens(uid)

    if format == "json":
        return JSONResponse(tokens)

    dest = _safe_next(next)
    resp = RedirectResponse(dest, status_code=303)
    set_jwt_cookie(resp, tokens["access_token"], request)
    logger.info("connect: web session for uid=%s → %s", uid, dest)
    return resp
