"""Універсальні Telegram-логін-лінки: бот → один тап → авторизований ендпоінт.

Бот ДОВІРЯЄ відправнику (Telegram підписує апдейти, ми знаємо `user_id`), тож мінтить
one-time токен, прив'язаний до user_id + цільового каналу. Токен живе в Redis з TTL.

Канали (`target`):
  * **web** — `/connect/<token>` обмінює токен на JWT, кладе його в HttpOnly-cookie і
    редіректить у консоль. Один тап у Telegram → браузер уже залогінений.
  * **app** — мобільний застосунок: `jarvis://pair?...` deeplink (обмін на `/api/v1/auth/pair`).
  * **ext** — браузерне розширення: видаємо JWT для вставки в popup (server URL + token).

Єдиний модуль для всіх Telegram-каналів входу — раніше логіка була розмазана по
`applogin.py` (pair) + `client_api/router.py` (tgauth) + `bot/apk.py`. Тут — спільний
мінт/редім; специфіку каналу (deeplink/JWT/cookie) додають місця виклику.
"""
from __future__ import annotations

import secrets

import redis.asyncio as aioredis

from jarvis_core.context import DEFAULT_ORG_ID, redis_key

# Валідні цільові канали логін-лінка.
TARGETS = ("web", "app", "ext")
DEFAULT_TTL = 600  # 10 хв — досить, щоб встигнути відкрити в браузері/застосунку


def _key(token: str) -> str:
    return redis_key(DEFAULT_ORG_ID, "connect", token)


async def mint(
    redis: aioredis.Redis, user_id: int, target: str = "web", ttl: int = DEFAULT_TTL
) -> str:
    """Створює one-time connect-токен `user_id` + `target`. Повертає токен (urlsafe)."""
    if target not in TARGETS:
        target = "web"
    token = secrets.token_urlsafe(18)
    await redis.setex(_key(token), ttl, f"{user_id}:{target}")
    return token


async def redeem(redis: aioredis.Redis, token: str) -> tuple[int, str] | None:
    """Одноразово обмінює токен на `(user_id, target)`. None — невалідний/прострочений."""
    token = (token or "").strip()
    if not token:
        return None
    raw = await redis.get(_key(token))
    if not raw:
        return None
    await redis.delete(_key(token))  # one-time
    val = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    uid_s, _, target = val.partition(":")
    try:
        return int(uid_s), (target or "web")
    except (ValueError, TypeError):
        return None
