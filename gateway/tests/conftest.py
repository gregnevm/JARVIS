"""Спільні pytest-фікстури gateway."""
from __future__ import annotations

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_startup_net(monkeypatch):
    """R1 «Тонкий шлюз»: тести ганяються повністю без стартової мережі.

    GATEWAY_STARTUP_NET=false глушить webhook/BotFather-UI і всі фонові поллери в
    lifespan — TestClient стартує миттєво і без жодного зовнішнього I/O.

    Docker-хости (redis/tools/…) локально недосяжні, але кожен фейл коштує ~2-4s
    (Windows ретраїть connect до закритого порту; admin-probe-и й redis-виклики
    давали до 40s на тест). 0.0.0.0:1 фейлиться миттєво на Windows (OSError) і
    Linux-CI (refused без SYN-ретраїв) з тією ж семантикою «сервіс недосяжний».
    Тест, якому треба інша адреса, перевизначає settings сам."""
    monkeypatch.setattr(settings, "gateway_startup_net", False)
    monkeypatch.setattr(settings, "redis_url", "redis://0.0.0.0:1/0")
    for field in ("tools_url", "memory_url", "twin_url", "whisper_url", "tts_url"):
        monkeypatch.setattr(settings, field, "http://0.0.0.0:1")


@pytest.fixture
def platform_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    with TestClient(app) as client:
        yield client
