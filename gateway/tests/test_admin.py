import asyncio

from app.auth import is_admin
from app.bot.admin import execute_action, is_admin_command
from app.config import settings


def test_is_admin_command():
    assert is_admin_command("/admin")
    assert is_admin_command("/confirm abc123")


def test_is_admin_fallback_to_allowed(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "admin_user_ids", "")
    assert is_admin(42)


def test_is_admin_explicit(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "1,2")
    monkeypatch.setattr(settings, "admin_user_ids", "99")
    assert is_admin(99)
    assert not is_admin(1)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.deleted: list[str] = []

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, *keys):
        for k in keys:
            self.deleted.append(k)
            self.store.pop(k, None)


class FakeSvc:
    async def reset_mode(self):
        return {"mode": "hybrid", "status": "reset"}

    async def set_mode(self, mode):
        return {"mode": mode, "status": "ok"}


def test_execute_reset_mode():
    async def _run():
        return await execute_action("mode:reset", FakeSvc(), FakeRedis())

    assert "hybrid" in asyncio.run(_run())
