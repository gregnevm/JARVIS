"""APK auto-deliver: gateway тягне свіжий реліз і DM-ить адмінам (дедуп по версії)."""
from __future__ import annotations

import asyncio
import types

import pytest

from app import apk_autodeliver
from app.config import settings


class FakeRedis:
    def __init__(self, kv=None):
        self.kv = dict(kv or {})

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v):
        self.kv[k] = v


class FakeTg:
    pass


def _patch(monkeypatch, *, remote, local, sent_holder, download_ok=True):
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "telegram_bot_token", "x")

    async def _remote(_client):
        return remote

    async def _dl(_client, _url, _dest):
        return download_ok

    async def _notify(_tg, admins):
        sent_holder.append(list(admins))
        return len(admins)

    monkeypatch.setattr(apk_autodeliver, "_fetch_remote_version", _remote)
    monkeypatch.setattr(apk_autodeliver, "_download", _dl)
    monkeypatch.setattr(apk_autodeliver, "notify_admins_apk_ready", _notify)
    monkeypatch.setattr(
        apk_autodeliver,
        "apk_info",
        lambda: (types.SimpleNamespace(version=local) if local else None),
    )
    # apk_path лише для local_v != remote (download) — не чіпаємо реальний FS у _download-мок.
    monkeypatch.setattr(apk_autodeliver, "apk_path", lambda: __import__("pathlib").Path("/tmp/none.apk"))


def test_delivers_when_remote_newer(monkeypatch):
    sent: list = []
    _patch(monkeypatch, remote="1.0.1", local="1.0.0", sent_holder=sent)
    redis = FakeRedis()
    ok = asyncio.run(apk_autodeliver.check_once(FakeTg(), redis))
    assert ok is True
    assert sent == [[42]]
    assert redis.kv[apk_autodeliver._DELIVERED_KEY] == "1.0.1"  # дедуп-маркер записано


def test_skips_when_version_already_delivered(monkeypatch):
    sent: list = []
    _patch(monkeypatch, remote="1.0.1", local="1.0.0", sent_holder=sent)
    redis = FakeRedis({apk_autodeliver._DELIVERED_KEY: "1.0.1"})
    ok = asyncio.run(apk_autodeliver.check_once(FakeTg(), redis))
    assert ok is False
    assert sent == []  # не спамимо тією самою версією


def test_no_redis_uses_local_file_as_marker(monkeypatch):
    # без Redis: локальний файл == remote → вважаємо доставленим, не шлемо
    sent: list = []
    _patch(monkeypatch, remote="1.0.1", local="1.0.1", sent_holder=sent)
    ok = asyncio.run(apk_autodeliver.check_once(FakeTg(), None))
    assert ok is False
    assert sent == []


def test_skips_without_admins(monkeypatch):
    sent: list = []
    _patch(monkeypatch, remote="1.0.1", local="1.0.0", sent_holder=sent)
    monkeypatch.setattr(settings, "admin_user_ids", "")
    monkeypatch.setattr(settings, "allowed_user_ids", "")
    ok = asyncio.run(apk_autodeliver.check_once(FakeTg(), FakeRedis()))
    assert ok is False and sent == []


def test_skips_when_release_unreachable(monkeypatch):
    sent: list = []
    _patch(monkeypatch, remote=None, local="1.0.0", sent_holder=sent)
    ok = asyncio.run(apk_autodeliver.check_once(FakeTg(), FakeRedis()))
    assert ok is False and sent == []
