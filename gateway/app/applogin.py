"""One-tap login link для мобільного застосунку.

Бот мінтить токен, ВЖЕ прив'язаний до Telegram-id того, хто просить (бо бот знає
відправника) — тож обмін не потребує жодного Telegram-раунду. Посилання
`jarvis://pair?server=…&token=…` → один тап у Telegram → застосунок відкривається
авторизованим (ChatActivity ловить deeplink → /api/v1/auth/pair → JWT).
"""
from __future__ import annotations

import secrets

import redis.asyncio as aioredis

from jarvis_core.context import DEFAULT_ORG_ID, redis_key

from .config import settings

_PAIR_TTL = 600  # 10 хв


def server_origin() -> str:
    """Базовий origin сервера для deeplink (публічний URL → інакше локальний)."""
    raw = (settings.public_app_url or settings.gateway_browser_url or "").strip()
    for suf in ("/app", "/platform"):
        if raw.endswith(suf):
            raw = raw[: -len(suf)]
    return raw.rstrip("/")


async def mint_login_link(redis: aioredis.Redis, user_id: int, ttl: int = _PAIR_TTL) -> str:
    """Створює one-time pairing-токен (прив'язаний до user_id) → deeplink jarvis://pair."""
    token = secrets.token_urlsafe(18)
    await redis.setex(redis_key(DEFAULT_ORG_ID, "apk", "pair", token), ttl, str(user_id))
    return f"jarvis://pair?server={server_origin()}&token={token}"
