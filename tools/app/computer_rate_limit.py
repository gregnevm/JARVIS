"""Ліміт мутуючих Computer Use дій на годину (Redis)."""
from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger("jarvis.tools.computer_rate_limit")

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _hour_key(user_id: int) -> str:
    hour = int(time.time() // 3600)
    return f"jarvis:computer:rl:{int(user_id)}:{hour}"


async def check_mutating_allowed(user_id: int) -> str | None:
    """None = OK, інакше текст помилки для користувача."""
    cap = settings.computer_rate_limit_per_hour
    if cap <= 0 or int(user_id) <= 0:
        return None
    key = _hour_key(user_id)
    try:
        raw = await _client().get(key)
        count = int(raw or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("computer rate limit check failed (fail-open): %s", exc)
        return None
    if count >= cap:
        return (
            f"Ліміт computer-дій вичерпано ({cap}/год). "
            "Спробуй пізніше або звернись до адміна."
        )
    return None


async def record_mutating(user_id: int) -> None:
    cap = settings.computer_rate_limit_per_hour
    if cap <= 0 or int(user_id) <= 0:
        return
    key = _hour_key(user_id)
    try:
        pipe = _client().pipeline()
        pipe.incr(key)
        pipe.expire(key, 7200)
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("computer rate limit record failed: %s", exc)
