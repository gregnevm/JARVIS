"""One-tap login link: mint_login_link прив'язує токен до user_id і будує deeplink."""
from __future__ import annotations

import pytest

from app import applogin
from app.config import settings


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def setex(self, k, ttl, v):
        self.kv[k] = (ttl, v)


async def test_mint_login_link_binds_uid(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "https://jarvis.example.com/app")
    r = FakeRedis()
    link = await applogin.mint_login_link(r, 42)
    assert link.startswith("jarvis://pair?server=https://jarvis.example.com&token=")
    # токен збережено в redis, прив'язаний до uid, з TTL
    (key, (ttl, val)) = next(iter(r.kv.items()))
    assert "apk:pair:" in key and val == "42" and ttl == 600


async def test_server_origin_strips_suffix(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "gateway_browser_url", "http://192.168.0.5:8000/platform")
    assert applogin.server_origin() == "http://192.168.0.5:8000"
