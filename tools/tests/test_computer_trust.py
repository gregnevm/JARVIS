"""Trusted Computer Use session."""
import pytest

from app.computer_trust import grant_trust, is_trusted, revoke_trust, trust_level
from app.config import settings


class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.ttl_map: dict[str, int] = {}

    async def setex(self, key, ttl, val):
        self.kv[key] = val
        self.ttl_map[key] = int(ttl)

    async def get(self, key):
        return self.kv.get(key)

    async def ttl(self, key):
        return self.ttl_map.get(key, -2)

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.ttl_map.pop(k, None)


@pytest.mark.asyncio
async def test_trust_session(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.computer_trust.get_redis", lambda: fake)
    uid = 999001
    await revoke_trust(uid)
    assert not await is_trusted(uid)
    await grant_trust(uid, ttl=60)
    assert await is_trusted(uid)
    assert await trust_level(uid) == "session"
    await grant_trust(uid, ttl=60, full=True)
    assert await trust_level(uid) == "full"
    await revoke_trust(uid)
    assert not await is_trusted(uid)


@pytest.mark.asyncio
async def test_trust_ttl_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "computer_session_trust_minutes", 15)
    from app.computer_trust import trust_ttl_seconds

    assert trust_ttl_seconds() == 900
