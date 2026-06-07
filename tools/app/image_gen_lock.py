"""Блокування одночасної генерації зображень (VRAM policy)."""
from __future__ import annotations

from .redis_util import get_redis

_KEY = "jarvis:image_gen:busy"
_TTL = 600


async def try_acquire() -> bool:
    return bool(await get_redis().set(_KEY, "1", nx=True, ex=_TTL))


async def release() -> None:
    await get_redis().delete(_KEY)
