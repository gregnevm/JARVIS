"""Window endpoints (skip on non-Windows)."""
import sys

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "token", "secret")
    return TestClient(app)


def test_window_list_requires_token(client: TestClient):
    r = client.get("/window/list")
    assert r.status_code == 403


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_window_list_ok(client: TestClient):
    r = client.get("/window/list", headers={"X-Hostagent-Token": "secret"})
    assert r.status_code == 200
    assert "windows" in r.json()
