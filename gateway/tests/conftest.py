"""Спільні pytest-фікстури gateway."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _no_startup_net(monkeypatch):
    """R1 «Тонкий шлюз»: тести ганяються повністю без стартової мережі.

    GATEWAY_STARTUP_NET=false глушить webhook/BotFather-UI і всі фонові поллери в
    lifespan — TestClient стартує миттєво і без жодного зовнішнього I/O."""
    monkeypatch.setattr(settings, "gateway_startup_net", False)


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
