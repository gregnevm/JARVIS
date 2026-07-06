"""Авторизація Platform-консолі.

Три канали (усі **admin-only** — консоль керує ключами/автопілотом, не даємо не-адміну):
  * Telegram Mini App  — `X-Telegram-Init-Data` HMAC, лише ADMIN_USER_IDS (`authorize_admin`);
  * Cookie one-tap     — `jarvis_jwt` з `/connect`, звірка `is_admin(uid)` (токен мінтиться
                         для будь-кого allowed, тож без цієї звірки друг ≠ адмін пройшов би);
  * Браузер (LAN)      — HTTP Basic, пароль PLATFORM_PASSWORD або ADMIN_PANEL_PASSWORD.

Reuse: `telegram_webapp_auth.authorize_admin`, `auth.is_admin`. Дублювати логіку `/admin`
не треба — просто приймаємо обидва паролі, щоб Platform не вимагав окремого секрету.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jarvis_core.context import RequestContext, synthetic_context

from ..auth import is_admin
from ..auth_channels import jwt_uid
from ..config import settings
from ..telegram_webapp_auth import authorize_admin

_security = HTTPBasic(auto_error=False)


@dataclass(frozen=True)
class PlatformAuth:
    """Хто і як зайшов: via=telegram|cookie|basic, user_id для runtime-запитів."""

    via: str
    user_id: int


def resolve_uid(auth: "PlatformAuth", user_id: int | None) -> int:
    """uid з query/body, якщо заданий (admin може запитувати від імені іншого user_id),
    інакше — uid автентифікованого користувача. Той самий патерн повторювався
    у кожному platform-роуті (`int(user_id) if user_id is not None else auth.user_id`).

    Anti-IDOR (AGENTS §5): cross-uid (діяти від імені ІНШОГО user_id) дозволено лише
    справжньому адміну. Сьогодні всі три канали platform-auth = admin-only, тож guard
    no-op; але він стає load-bearing, щойно постануть non-owner ролі (SaaS PR#6) —
    тоді не-адмін не зможе зімперсонити чужий uid через `?user_id=`."""
    if user_id is None or int(user_id) == auth.user_id:
        return auth.user_id
    admins = settings.admin_ids
    if admins and auth.user_id not in admins:
        raise HTTPException(status_code=403, detail="cross-user access requires admin")
    return int(user_id)


def resolve_context(
    auth: "PlatformAuth", user_id: int | None = None, *, request_id: str | None = None
) -> RequestContext:
    """PlatformAuth → RequestContext (SAAS_DEEP_DIVE §2.2; tenant-ґрунт PR#1).

    Self-hosted (`SAAS_MODE=false`): synthetic org, Telegram uid → `legacy_uid`,
    повний доступ (owner/studio). Коли постане SaaS (PR#6), сюди ляже branch на
    JWT/api_key з реальними org/role/plan. Поки що — обгортка над `resolve_uid`,
    тож self-hosted поведінка незмінна (S2)."""
    return synthetic_context(resolve_uid(auth, user_id), via=auth.via, request_id=request_id)


def _primary_admin_id() -> int:
    ids = sorted(settings.admin_ids)
    return ids[0] if ids else 0


def _password() -> str:
    """Активний пароль браузерного входу (PLATFORM_PASSWORD має пріоритет)."""
    return (settings.platform_password.strip() or settings.admin_panel_password.strip())


def platform_enabled() -> bool:
    """Браузерний вхід доступний лише якщо задано пароль."""
    return bool(_password())


def primary_admin_id() -> int:
    """Публічний доступ до основного admin uid (для client-API JWT subject, CL-1)."""
    return _primary_admin_id()


def verify_admin_password(username: str, password: str) -> bool:
    """Перевірка admin-логіну (PLATFORM_PASSWORD/ADMIN_PANEL_PASSWORD) для client-API.

    Reuse тієї самої логіки, що й браузерний Basic-вхід — щоб JWT-логін (CL-1.1) не
    дублював перевірку пароля. False, якщо пароль не заданий (вхід вимкнено)."""
    return platform_enabled() and _check_credentials(username, password)


def _check_credentials(username: str, password: str) -> bool:
    want_user = settings.admin_panel_user.strip() or "admin"
    want_pass = _password()
    if not want_pass:
        return False
    user_ok = secrets.compare_digest(username.encode(), want_user.encode())
    pass_ok = secrets.compare_digest(password.encode(), want_pass.encode())
    return user_ok and pass_ok


def require_platform_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    jarvis_jwt: str | None = Cookie(default=None),
) -> PlatformAuth:
    if x_telegram_init_data:
        uid = authorize_admin(x_telegram_init_data)
        return PlatformAuth(via="telegram", user_id=uid)
    # JWT-cookie з Telegram one-tap (`/connect`) — браузерна сесія без пароля.
    # Декод — спільний примітив (auth_channels.jwt_uid); битий/прострочений → None.
    cookie_uid = jwt_uid(jarvis_jwt)
    if cookie_uid is not None:
        # Cookie-канал admin-only, як initData (authorize_admin) і Basic (_primary_admin_id):
        # `/connect` мінтить JWT для БУДЬ-КОГО allowed (друг з ALLOWED_USER_IDS чи /allow),
        # а не лише admin. Без цієї звірки не-адмін через one-tap отримував повний доступ
        # до developer-консолі (створення/відкликання sk-jarvis-* ключів, usage, логи).
        # Не-адмін → не повертаємо: падаємо у Basic/401/503 нижче (як битий cookie).
        if is_admin(cookie_uid):
            return PlatformAuth(via="cookie", user_id=cookie_uid)
    if platform_enabled():
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="authentication required",
                headers={"WWW-Authenticate": 'Basic realm="JARVIS Platform"'},
            )
        if not _check_credentials(credentials.username, credentials.password):
            raise HTTPException(
                status_code=401,
                detail="invalid credentials",
                headers={"WWW-Authenticate": 'Basic realm="JARVIS Platform"'},
            )
        return PlatformAuth(via="basic", user_id=_primary_admin_id())
    raise HTTPException(
        status_code=503,
        detail="Platform: увійди через Telegram (/platform) або задай PLATFORM_PASSWORD",
    )
