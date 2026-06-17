"""JWT auth для client-API (CL-1.1) — токени для клієнтів без Telegram initData (mobile APK, SPA).

**Скоуп self-hosted MVP:** один admin логіниться `PLATFORM_PASSWORD` → JWT із synthetic org
(owner/studio). Реальний multi-user signup/login із таблицею `users` — SAAS PR#6.

**За прапором (S2):** порожній `JWT_SECRET` → `jwt_enabled()=False`, JWT-ендпоінти віддають 503;
self-hosted (initData/Basic) працює як раніше.

HS256, claims: `sub` (uid), `org`, `role`, `plan`, `legacy_uid`, `type` (access|refresh), `iat`, `exp`.
"""
from __future__ import annotations

import time
from typing import Any

import jwt

from jarvis_core.context import DEFAULT_ORG_ID, RequestContext

from ..config import settings


class JWTError(Exception):
    """Невалідний / прострочений / не того типу токен."""


def jwt_enabled() -> bool:
    """JWT-логін активний лише якщо заданий секрет (інакше лишаються initData/Basic)."""
    return bool(settings.jwt_secret.strip())


def _now() -> int:
    return int(time.time())


def _encode(payload: dict[str, Any], ttl: int) -> str:
    now = _now()
    body = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def issue_access(
    uid: int, *, org_id: str | None = None, role: str = "owner", plan: str = "studio"
) -> str:
    return _encode(
        {
            "sub": str(uid),
            "org": org_id or settings.default_org_id or DEFAULT_ORG_ID,
            "role": role,
            "plan": plan,
            "legacy_uid": int(uid),
            "type": "access",
        },
        settings.jwt_access_ttl,
    )


def issue_refresh(uid: int, *, org_id: str | None = None) -> str:
    return _encode(
        {
            "sub": str(uid),
            "org": org_id or settings.default_org_id or DEFAULT_ORG_ID,
            "type": "refresh",
        },
        settings.jwt_refresh_ttl,
    )


def issue_tokens(
    uid: int, *, org_id: str | None = None, role: str = "owner", plan: str = "studio"
) -> dict[str, Any]:
    """Пара токенів + метадані для клієнта (формат як в OAuth2 token response)."""
    return {
        "access_token": issue_access(uid, org_id=org_id, role=role, plan=plan),
        "refresh_token": issue_refresh(uid, org_id=org_id),
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl,
    }


def decode(token: str, *, expect: str = "access") -> dict[str, Any]:
    """Декодувати+верифікувати токен. Кидає `JWTError` на будь-яку проблему / невідповідність типу."""
    if not jwt_enabled():
        raise JWTError("jwt disabled")
    try:
        claims: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise JWTError(str(exc)) from exc
    if claims.get("type") != expect:
        raise JWTError(f"expected {expect} token, got {claims.get('type')}")
    return claims


def context_from_claims(claims: dict[str, Any]) -> RequestContext:
    """JWT claims → RequestContext (via=jwt). org/role/plan із токена; self-hosted — synthetic.

    Кидає `JWTError`, якщо обов'язковий `sub` відсутній — щоб виклик у resolver впав у
    `except JWTError` і дав 401, а не 500 (малформ підписаного токена не має валити процес)."""
    sub = claims.get("sub")
    if sub is None:
        raise JWTError("missing sub claim")
    legacy = claims.get("legacy_uid")
    try:
        legacy_uid = int(legacy) if legacy is not None else None
    except (ValueError, TypeError):
        legacy_uid = None
    return RequestContext(
        org_id=str(claims.get("org") or DEFAULT_ORG_ID),
        user_id=str(sub),
        role=str(claims.get("role", "owner")),
        plan=str(claims.get("plan", "studio")),
        legacy_uid=legacy_uid,
        via="jwt",
    )
