"""Перевірка секрету вебхука: /webhook має відкидати апдейти без правильного заголовка."""
from typing import Any

from fastapi.testclient import TestClient

import app.main as main
from app.config import settings


async def _noop(update: dict[str, Any], app: Any) -> None:
    """Підміна _process — щоб не ходити в мережу під час тесту."""
    return None


def test_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    monkeypatch.setattr(main, "_process", _noop)
    with TestClient(main.app) as c:
        r = c.post("/webhook", json={"x": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert r.status_code == 403


def test_rejects_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    monkeypatch.setattr(main, "_process", _noop)
    with TestClient(main.app) as c:
        r = c.post("/webhook", json={"x": 1})  # без заголовка
    assert r.status_code == 403


def test_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    monkeypatch.setattr(main, "_process", _noop)
    with TestClient(main.app) as c:
        r = c.post("/webhook", json={"x": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_no_secret_configured_accepts_any(monkeypatch):
    # Порожній секрет → перевірка вимкнена (бекв-сумісно).
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    monkeypatch.setattr(main, "_process", _noop)
    with TestClient(main.app) as c:
        r = c.post("/webhook", json={"x": 1})
    assert r.status_code == 200
