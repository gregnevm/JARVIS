"""Telegram-логін мобільного застосунку: /api/v1/auth/telegram/{start,poll}."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-key-cl1-min-32-bytes-long-abcd")


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, k, ttl, v):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, k):
        self.store.pop(k, None)

    async def aclose(self):
        return None


class FakeTg:
    async def get_me(self):
        return {"username": "jarvisbot"}

    async def aclose(self):
        return None


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    with TestClient(app) as c:
        app.state.redis = FakeRedis()
        app.state.tg = FakeTg()
        yield c


def test_start_returns_deeplink(client):
    r = client.post("/api/v1/auth/telegram/start")
    assert r.status_code == 200
    d = r.json()
    assert d["bot_username"] == "jarvisbot"
    assert d["deeplink"].startswith("https://t.me/jarvisbot?start=tgauth_")
    assert d["token"]


def test_poll_pending_then_bound_then_expired(client):
    token = client.post("/api/v1/auth/telegram/start").json()["token"]
    # ще не підтверджено в Telegram
    assert client.post("/api/v1/auth/telegram/poll", json={"token": token}).json()["status"] == "pending"
    # бот прив'язав uid (емуляція /start tgauth_<token>)
    app.state.redis.store[f"tgauth:{token}"] = "42"
    r = client.post("/api/v1/auth/telegram/poll", json={"token": token})
    body = r.json()
    assert body["status"] == "ok" and body["access_token"]
    # one-time → другий poll = expired
    assert client.post("/api/v1/auth/telegram/poll", json={"token": token}).json()["status"] == "expired"


def test_poll_unknown_token_expired(client):
    assert client.post("/api/v1/auth/telegram/poll", json={"token": "nope"}).json()["status"] == "expired"
