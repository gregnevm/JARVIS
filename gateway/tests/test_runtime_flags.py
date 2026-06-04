"""Runtime flags in Redis."""
import asyncio

from app.runtime_flags import get_flags, set_flag, streaming_enabled, voice_reply_enabled


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, val):
        self.data[key] = val


def _run(coro):
    return asyncio.run(coro)


def test_flags_default_from_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_streaming", True)
    monkeypatch.setattr(settings, "enable_voice_reply", False)
    redis = FakeRedis()
    assert _run(streaming_enabled(redis)) is True
    assert _run(voice_reply_enabled(redis)) is False


def test_flags_override(monkeypatch):
    redis = FakeRedis()
    _run(set_flag(redis, "streaming", False))
    _run(set_flag(redis, "voice_reply", True))
    fl = _run(get_flags(redis))
    assert fl["streaming"] is False
    assert fl["voice_reply"] is True
