"""ntfy push (BE3): guard-логіка + успішна публікація з фейковим httpx-клієнтом."""
from __future__ import annotations

from app import push
from app.config import settings


async def test_disabled_returns_false(monkeypatch):
    monkeypatch.setattr(settings, "push_enabled", False)
    assert await push.publish("hi") is False


async def test_empty_topic_returns_false(monkeypatch):
    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_topic", "")
    assert await push.publish("hi") is False


async def test_empty_message_returns_false(monkeypatch):
    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_topic", "jarvis-u42")
    assert await push.publish("   ") is False


class _FakeResp:
    def raise_for_status(self) -> None: ...


class _FakeClient:
    def __init__(self, *a, **k): self.posted = None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, **k):
        _FakeClient.last_url = url
        _FakeClient.last_body = k.get("content")
        _FakeClient.last_headers = k.get("headers") or {}
        return _FakeResp()


async def test_publish_success(monkeypatch):
    import jarvis_core.push as core_push

    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_url", "https://ntfy.sh")
    monkeypatch.setattr(settings, "ntfy_topic", "jarvis-u42")
    # Транспорт тепер SSOT у jarvis_core.push — мокаємо httpx там.
    monkeypatch.setattr(core_push.httpx, "AsyncClient", _FakeClient)
    ok = await push.publish("Пропозиції: передзвонити мамі", title="JARVIS")
    assert ok is True
    assert _FakeClient.last_url == "https://ntfy.sh/jarvis-u42"
    assert "мамі".encode("utf-8") in _FakeClient.last_body


async def test_publish_click_deep_link(monkeypatch):
    import jarvis_core.push as core_push

    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_url", "https://ntfy.sh")
    monkeypatch.setattr(settings, "ntfy_topic", "jarvis-u42")
    monkeypatch.setattr(core_push.httpx, "AsyncClient", _FakeClient)
    ok = await push.publish("Підтвердь дію", click="https://app.example/app")
    assert ok is True
    assert _FakeClient.last_headers.get("Click") == "https://app.example/app"
