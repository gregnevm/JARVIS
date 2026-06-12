"""Trusted Computer Use session — без повторного ✅ на T0/T1 (і опційно всі tier)."""
from __future__ import annotations

from .config import settings
from .redis_util import get_redis

_TRUST_PREFIX = "jarvis:computer:trust:"
_TRUST_FULL = "full"
_TRUST_SESSION = "session"


def _key(user_id: int) -> str:
    return f"{_TRUST_PREFIX}{int(user_id)}"


def trust_ttl_seconds(*, full: bool = False) -> int:
    """TTL у секундах для grant_trust."""
    mins = int(settings.computer_session_trust_minutes or 0)
    if mins <= 0:
        return 0
    return mins * 60


async def is_trusted(user_id: int) -> bool:
    return (await trust_level(user_id)) is not None


async def trust_level(user_id: int) -> str | None:
    """Повертає 'session' | 'full' або None."""
    if int(user_id) <= 0:
        return None
    try:
        raw = await get_redis().get(_key(user_id))
        if raw is None:
            return None
        val = raw.decode() if isinstance(raw, bytes) else str(raw)
        if val in (_TRUST_SESSION, _TRUST_FULL):
            ttl = await get_redis().ttl(_key(user_id))
            if ttl is not None and ttl > 0:
                return val
        return None
    except Exception:
        return None


async def grant_trust(user_id: int, ttl: int | None = None, *, full: bool = False) -> None:
    if int(user_id) <= 0:
        return
    seconds = ttl if ttl is not None else trust_ttl_seconds(full=full)
    if seconds <= 0:
        return
    mode = _TRUST_FULL if full else _TRUST_SESSION
    await get_redis().setex(_key(user_id), seconds, mode)


async def revoke_trust(user_id: int) -> None:
    await get_redis().delete(_key(user_id))


async def trust_remaining(user_id: int) -> int:
    ttl = await get_redis().ttl(_key(user_id))
    return max(0, int(ttl)) if ttl is not None else 0
