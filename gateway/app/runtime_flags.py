"""Runtime-прапори gateway (streaming, voice) — Redis, fallback на .env."""
from __future__ import annotations

import redis.asyncio as aioredis

from .config import settings

_KEY_STREAM = "jarvis:flags:streaming"
_KEY_VOICE = "jarvis:flags:voice"


async def streaming_enabled(redis: aioredis.Redis | None) -> bool:
    if redis is None:
        return settings.enable_streaming
    raw = await redis.get(_KEY_STREAM)
    if raw is None:
        return settings.enable_streaming
    return raw.lower() in ("1", "true", "yes", "on")


async def voice_reply_enabled(redis: aioredis.Redis | None) -> bool:
    if redis is None:
        return settings.enable_voice_reply
    raw = await redis.get(_KEY_VOICE)
    if raw is None:
        return settings.enable_voice_reply
    return raw.lower() in ("1", "true", "yes", "on")


async def get_flags(redis: aioredis.Redis | None) -> dict[str, bool]:
    return {
        "streaming": await streaming_enabled(redis),
        "voice_reply": await voice_reply_enabled(redis),
        "streaming_default": settings.enable_streaming,
        "voice_default": settings.enable_voice_reply,
    }


async def set_flag(redis: aioredis.Redis, name: str, enabled: bool) -> None:
    key = _KEY_STREAM if name == "streaming" else _KEY_VOICE if name == "voice_reply" else ""
    if not key:
        raise ValueError("unknown flag")
    await redis.set(key, "1" if enabled else "0")
