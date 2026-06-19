"""Rate limiting на user_id через Redis (фіксоване вікно 60с).

Якщо Redis недоступний — НЕ блокуємо користувача (fail-open): краще пропустити
зайвий запит, ніж покласти бота через проблеми з кешем.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from jarvis_core.context import DEFAULT_ORG_ID, redis_key

logger = logging.getLogger("jarvis.ratelimit")


class _RedisLike(Protocol):
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, seconds: int) -> Any: ...


class RateLimiter:
    def __init__(self, redis: _RedisLike | None, limit_per_min: int) -> None:
        self._redis = redis
        self._limit = limit_per_min

    @property
    def limit(self) -> int:
        """Налаштований дефолтний cap/хв (для rate-limit заголовків на 429)."""
        return self._limit

    async def allow(
        self, user_id: int, *, limit: int | None = None, org_id: str | None = None
    ) -> bool:
        cap = self._limit if limit is None else limit
        if cap <= 0 or self._redis is None:
            return True
        window = int(time.time() // 60)
        # Org-префіксований ключ (AGENTS §5): `jarvis:{org_id}:rl:{user_id}:{window}`.
        # Self-hosted = синтетична org; під SaaS org розділяє лічильники між тенантами.
        key = redis_key(org_id or DEFAULT_ORG_ID, "rl", str(user_id), str(window))
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
        except Exception as exc:  # noqa: BLE001 — Redis впав → пропускаємо
            logger.warning("rate limit check failed (fail-open): %s", exc)
            return True
        return count <= cap
