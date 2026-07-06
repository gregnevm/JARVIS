"""screen/click endpoint."""
import sys

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "token", "secret")
    return TestClient(app)


def test_screen_click_requires_token(client: TestClient):
    r = client.post("/screen/click", json={"x": 10, "y": 20})
    assert r.status_code == 403


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_screen_click_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.main._run_powershell",
        lambda *a, **k: {"stdout": "", "stderr": "", "code": 0},
    )
    r = client.post(
        "/screen/click",
        json={"x": 100, "y": 200},
        headers={"X-Hostagent-Token": "secret"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
