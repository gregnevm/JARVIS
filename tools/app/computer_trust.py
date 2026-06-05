"""Trusted Computer Use session — 30 хв без ✅ на mutating дії."""
from __future__ import annotations

import redis.asyncio as aioredis

from .config import settings

_TRUST_PREFIX = "jarvis:computer:trust:"
TRUST_TTL = 1800


_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _key(user_id: int) -> str:
    return f"{_TRUST_PREFIX}{int(user_id)}"


async def is_trusted(user_id: int) -> bool:
    if int(user_id) <= 0:
        return False
    try:
        raw = await _client().ttl(_key(user_id))
        return raw is not None and raw > 0
    except Exception:
        return False


async def grant_trust(user_id: int, ttl: int = TRUST_TTL) -> None:
    if int(user_id) <= 0:
        return
    await _client().setex(_key(user_id), ttl, "1")


async def revoke_trust(user_id: int) -> None:
    await _client().delete(_key(user_id))


async def trust_remaining(user_id: int) -> int:
    ttl = await _client().ttl(_key(user_id))
    return max(0, int(ttl)) if ttl is not None else 0
