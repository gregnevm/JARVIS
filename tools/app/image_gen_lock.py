"""Блокування одночасної генерації зображень (VRAM policy)."""
from __future__ import annotations

import redis.asyncio as aioredis

from .config import settings

_KEY = "jarvis:image_gen:busy"
_TTL = 600

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def try_acquire() -> bool:
    return bool(await _client().set(_KEY, "1", nx=True, ex=_TTL))


async def release() -> None:
    await _client().delete(_KEY)
