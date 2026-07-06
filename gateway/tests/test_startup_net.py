"""R1 «Тонкий шлюз»: стартова мережа gateway — best-effort і вимикається прапором.

Критерії §1 спеки (docs/REFACTOR_THIN_GATEWAY.spec.md): у lifespan немає безумовних
мережевих await; webhook/BotFather-UI реєструються фоновою best-effort таскою;
GATEWAY_STARTUP_NET=false глушить стартову мережу повністю.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.telegram import TelegramClient


def _tg_with_recorder(seen: list[str]) -> TelegramClient:
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"ok": True, "result": True})

    tg = TelegramClient("TOKEN")
    tg._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return tg


def _app_stub(tg: TelegramClient) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(tg=tg, bot_ui_registered=False))


def test_startup_net_polling_registers_bot_ui(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "")
    seen: list[str] = []
    tg = _tg_with_recorder(seen)
    app = _app_stub(tg)

    async def _run() -> None:
        try:
            await main._startup_net(app, "polling")
        finally:
            await tg.aclose()

    asyncio.run(_run())
    assert "setMyCommands" in seen
    assert "setWebhook" not in seen
    assert app.state.bot_ui_registered is True


def test_startup_net_webhook_registers_webhook_then_ui(monkeypatch):
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "telegram_webhook_url", "https://example.com/webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    seen: list[str] = []
    tg = _tg_with_recorder(seen)
    app = _app_stub(tg)

    async def _run() -> None:
        try:
            await main._startup_net(app, "webhook")
        finally:
            await tg.aclose()

    asyncio.run(_run())
    assert seen[0] == "setWebhook"
    assert "setMyCommands" in seen
    assert app.state.bot_ui_registered is True


def test_startup_net_failure_is_best_effort(monkeypatch):
    """register_bot_ui кидає → жодного винятку назовні, bot_ui_registered лишається false.

    (HTTP-помилки TelegramClient ковтає сам; тут перевіряємо контракт таски —
    будь-який неочікуваний виняток не валить старт gateway.)"""

    async def boom(tg: object) -> None:
        raise RuntimeError("telegram down")

    monkeypatch.setattr(main, "register_bot_ui", boom)
    app = SimpleNamespace(state=SimpleNamespace(tg=None, bot_ui_registered=False))

    asyncio.run(main._startup_net(app, "polling"))  # не кидає — best-effort
    assert app.state.bot_ui_registered is False


def test_health_exposes_bot_ui_flag():
    with TestClient(main.app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "bot_ui_registered": False}


async def _noop_loop(*args: object, **kwargs: object) -> None:
    return None


def test_lifespan_skips_startup_net_by_default(monkeypatch):
    """Автофікстура (_no_startup_net) глушить прапор → стартова мережа не планується."""
    calls: list[str] = []

    async def fake_startup(app: object, mode: str) -> None:
        calls.append(mode)

    monkeypatch.setattr(main, "_startup_net", fake_startup)
    with TestClient(main.app):
        pass
    assert calls == []


def test_lifespan_schedules_startup_net_when_enabled(monkeypatch):
    calls: list[str] = []

    async def fake_startup(app: object, mode: str) -> None:
        calls.append(mode)

    monkeypatch.setattr(main, "_startup_net", fake_startup)
    monkeypatch.setattr(main, "reminder_loop", _noop_loop)
    monkeypatch.setattr(main, "job_runner_loop", _noop_loop)
    monkeypatch.setattr(main, "bg_job_runner_loop", _noop_loop)
    monkeypatch.setattr(settings, "gateway_startup_net", True)
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "telegram_ingest_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_url", "")
    with TestClient(main.app):
        pass
    assert calls == ["webhook"]
