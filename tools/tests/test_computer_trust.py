"""Trusted Computer Use session."""
import pytest

from app.computer_trust import grant_trust, is_trusted, revoke_trust


class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.ttl_map: dict[str, int] = {}

    async def setex(self, key, ttl, val):
        self.kv[key] = val
        self.ttl_map[key] = int(ttl)

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
    await revoke_trust(uid)
    assert not await is_trusted(uid)
