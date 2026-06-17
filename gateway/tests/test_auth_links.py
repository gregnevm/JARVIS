"""Універсальні Telegram-логін-лінки (`app/auth_links.py`) — мінт/редім."""
from __future__ import annotations

import asyncio

from app import auth_links


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, k: str, ttl: int, v: str) -> None:
        self.store[k] = v

    async def get(self, k: str):
        return self.store.get(k)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self.store.pop(k, None)


def test_mint_then_redeem_roundtrip():
    async def _run():
        r = FakeRedis()
        token = await auth_links.mint(r, 42, target="web")
        assert token
        info = await auth_links.redeem(r, token)
        assert info == (42, "web")

    asyncio.run(_run())


def test_redeem_is_one_time():
    async def _run():
        r = FakeRedis()
        token = await auth_links.mint(r, 7, target="ext")
        assert await auth_links.redeem(r, token) == (7, "ext")
        # другий редім — None (токен видалено)
        assert await auth_links.redeem(r, token) is None

    asyncio.run(_run())


def test_redeem_unknown_and_empty():
    async def _run():
        r = FakeRedis()
        assert await auth_links.redeem(r, "nope") is None
        assert await auth_links.redeem(r, "") is None

    asyncio.run(_run())


def test_unknown_target_falls_back_to_web():
    async def _run():
        r = FakeRedis()
        token = await auth_links.mint(r, 1, target="bogus")
        assert await auth_links.redeem(r, token) == (1, "web")

    asyncio.run(_run())
