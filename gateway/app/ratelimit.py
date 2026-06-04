"""Rate limiting на user_id через Redis (фіксоване вікно 60с).

Якщо Redis недоступний — НЕ блокуємо користувача (fail-open): краще пропустити
зайвий запит, ніж покласти бота через проблеми з кешем.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol

logger = logging.getLogger("jarvis.ratelimit")


class _RedisLike(Protocol):
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, seconds: int) -> Any: ...


class RateLimiter:
    def __init__(self, redis: _RedisLike | None, limit_per_min: int) -> None:
        self._redis = redis
        self._limit = limit_per_min

    async def allow(self, user_id: int, *, limit: int | None = None) -> bool:
        cap = self._limit if limit is None else limit
        if cap <= 0 or self._redis is None:
            return True
        window = int(time.time() // 60)
        key = f"rl:{user_id}:{window}"
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
        except Exception as exc:  # noqa: BLE001 — Redis впав → пропускаємо
            logger.warning("rate limit check failed (fail-open): %s", exc)
            return True
        return count <= cap
