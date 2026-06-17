"""Bot-хаб авторизації (`bot/auth_link.py`) — /connect меню + канали web/app/ext."""
from __future__ import annotations

import asyncio

import pytest

from app.bot import auth_link
from app.bot.commands import handle_command
from app.config import settings


class FakeTg:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict | None]] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self.sent.append((text, reply_markup))

    async def answer_callback_query(self, *a, **k):
        pass


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, k, ttl, v):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


def _texts(tg: FakeTg) -> str:
    return "\n".join(t for t, _ in tg.sent)


def test_connect_command_shows_menu(monkeypatch):
    tg = FakeTg()

    async def _run():
        await handle_command("/connect", 5, 42, tg, svc=None, redis=FakeRedis())

    asyncio.run(_run())
    # меню з трьома каналами
    kbs = [kb for _, kb in tg.sent if kb]
    flat = [b["callback_data"] for kb in kbs for row in kb["inline_keyboard"] for b in row]
    assert {"conn:web", "conn:app", "conn:ext"} <= set(flat)


def test_conn_web_emits_login_url(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "x" * 40)
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    tg, redis = FakeTg(), FakeRedis()

    async def _run():
        await auth_link.handle_connect_callback("conn:web", 5, 42, tg, redis)

    asyncio.run(_run())
    # згенеровано one-tap URL до /connect/<token>
    urls = [
        b.get("url")
        for _, kb in tg.sent
        if kb
        for row in kb["inline_keyboard"]
        for b in row
        if b.get("url")
    ]
    assert any("/connect/" in (u or "") for u in urls)
    # токен реально покладено в Redis (ключ містить namespace "connect")
    assert any("connect" in k for k in redis.store)


def test_conn_web_without_jwt_explains(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    tg, redis = FakeTg(), FakeRedis()

    async def _run():
        await auth_link.handle_connect_callback("conn:web", 5, 42, tg, redis)

    asyncio.run(_run())
    assert "JWT_SECRET" in _texts(tg)


def test_conn_ext_emits_server_and_token(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "y" * 40)
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    tg = FakeTg()

    async def _run():
        await auth_link.handle_connect_callback("conn:ext", 5, 42, tg, redis=None)

    asyncio.run(_run())
    body = _texts(tg)
    assert "Server" in body and "Token" in body
    assert "jarvis.example.com" in body


def test_conn_app_emits_pair_deeplink(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    tg, redis = FakeTg(), FakeRedis()

    async def _run():
        await auth_link.handle_connect_callback("conn:app", 5, 42, tg, redis)

    asyncio.run(_run())
    assert "jarvis://pair" in _texts(tg)


def test_connect_command_direct_ext_arg(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "z" * 40)
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    tg = FakeTg()

    async def _run():
        # `/connect ext` оминає меню й одразу видає server+token (redis не потрібен).
        await handle_command("/connect ext", 5, 42, tg, svc=None, redis=None)

    asyncio.run(_run())
    assert "Token" in _texts(tg)


def test_conn_menu_callback_reopens_menu():
    tg = FakeTg()

    async def _run():
        return await auth_link.handle_connect_callback("conn:menu", 5, 42, tg, FakeRedis())

    consumed = asyncio.run(_run())
    assert consumed is True
    assert "Підключити" in _texts(tg)
