"""R3.4 «Тонкий шлюз»: спільні канал-примітиви auth (P7 SSOT).

Обидва резолвери — `client_api/deps.resolve_client_context` (канонічний
`/api/v1`) і `platform/auth.require_platform_auth` (legacy `/platform/api`) —
тонкі адаптери над цими примітивами: кожен тримає СВІЙ порядок каналів і
політику (admin-gate на cookie, 401 vs 503 без пароля — це свідомі відмінності
контрактів), але парсинг заголовків і JWT-декод — одна точка істини тут.
"""
from __future__ import annotations

from jarvis_core.context import RequestContext

from .saas import auth as jwt_auth


def bearer_token(authorization: str | None) -> str | None:
    """Витягає токен із `Authorization: Bearer …` (None — нема/не bearer)."""
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


def jwt_request_context(token: str | None) -> RequestContext | None:
    """JWT → RequestContext; None — вимкнено/битий/прострочений (канал пропускається)."""
    if not token or not jwt_auth.jwt_enabled():
        return None
    try:
        return jwt_auth.context_from_claims(jwt_auth.decode(token))
    except jwt_auth.JWTError:
        return None


def jwt_uid(token: str | None) -> int | None:
    """JWT → числовий uid (`legacy_uid`, фолбек `sub`); None — битий/вимкнений.

    Адмін-гейт свідомо НЕ тут: політика каналу (напр. cookie у platform —
    admin-only) лишається в адаптері-резолвері."""
    if not token or not jwt_auth.jwt_enabled():
        return None
    try:
        claims = jwt_auth.decode(token)
        raw_uid = claims.get("legacy_uid")
        return int(raw_uid) if raw_uid is not None else int(claims["sub"])
    except (jwt_auth.JWTError, KeyError, ValueError, TypeError):
        return None
