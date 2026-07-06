"""CL-1.4 — єдиний auth-resolver для client-API.

Усі канали входу → один `RequestContext` (SAAS §2.2). Порядок спроб:
  1. **Bearer JWT** (mobile/SPA) — якщо `JWT_SECRET` заданий і токен валідний.
  2. **Telegram initData** (Mini App) — HMAC, лише адміни.
  3. **HTTP Basic** (браузер/CLI) — `PLATFORM_PASSWORD`.
  (api-key `sk-jarvis-*` per-org → AP-1, поки не реалізовано — global `/v1` ключ окремо в openai_api.)

Self-hosted: усі шляхи мапляться на synthetic org (owner/studio) — Telegram-flow незмінний (S2).
Жоден валідний канал не підійшов → 401. Це канонічний resolver для `/api/v1/*`; legacy
`/platform/api/*` лишається на власному `require_platform_auth` (повна консолідація — CL-1.3, поетапно).
"""
from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from jarvis_core.context import RequestContext, synthetic_context

from ..auth_channels import bearer_token, jwt_request_context
from ..platform.auth import primary_admin_id, verify_admin_password
from ..telegram_webapp_auth import authorize_admin

_security = HTTPBasic(auto_error=False)


def context_uid(ctx: RequestContext) -> int:
    """int-ключ для memory/tools: legacy_uid (Telegram id), фолбек на user_id.

    R3.4 «Тонкий шлюз»: єдине місце (раніше 6 побайтових копій `_uid` по
    client_api-модулях); 400 — коли контекст без числового id."""
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id")


def resolve_client_context(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    credentials: HTTPBasicCredentials | None = Depends(_security),
    jarvis_jwt: str | None = Cookie(default=None),
) -> RequestContext:
    # 1. Bearer JWT, або JWT-cookie (Telegram one-tap → `/connect` → cookie).
    #    Битий/вимкнений JWT → пробуємо інші канали, інакше фінальний 401.
    for token in (bearer_token(authorization), jarvis_jwt):
        ctx = jwt_request_context(token)
        if ctx is not None:
            return ctx

    # 2. Telegram initData (Mini App)
    if x_telegram_init_data:
        uid = authorize_admin(x_telegram_init_data)  # 401, якщо HMAC/admin не пройшов
        return synthetic_context(uid, via="telegram")

    # 3. HTTP Basic
    if credentials is not None and verify_admin_password(credentials.username, credentials.password):
        return synthetic_context(primary_admin_id(), via="basic")

    raise HTTPException(
        status_code=401,
        detail="authentication required (JWT Bearer, Telegram initData, або Basic)",
        headers={"WWW-Authenticate": 'Basic realm="JARVIS Client API"'},
    )
