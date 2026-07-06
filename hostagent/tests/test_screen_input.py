"""screen/type, hotkey, scroll endpoints + PS builders."""
from __future__ import annotations

import sys

import pytest
from app.config import settings
from app.main import app
from app.screen_input import build_hotkey_ps, build_scroll_ps, build_type_ps
from fastapi.testclient import TestClient


def test_build_type_ps_short():
    ps = build_type_ps("hi")
    assert "SendKeys" in ps
    assert "hi" in ps or "hi" in ps.lower()


def test_build_type_ps_long_uses_clipboard():
    ps = build_type_ps("x" * 100)
    assert "Clipboard" in ps
    assert "^v" in ps


def test_build_hotkey_ctrl_s():
    ps = build_hotkey_ps(["ctrl", "s"])
    assert "^s" in ps


def test_build_scroll_ps():
    ps = build_scroll_ps(-3)
    assert "0x0800" in ps
    assert "-360" in ps


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "token", "secret")
    return TestClient(app)


def test_screen_type_requires_token(client: TestClient):
    r = client.post("/screen/type", json={"text": "a"})
    assert r.status_code == 403


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_screen_type_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.main._run_powershell",
        lambda *a, **k: {"stdout": "", "stderr": "", "code": 0},
    )
    r = client.post(
        "/screen/type",
        json={"text": "hello"},
        headers={"X-Hostagent-Token": "secret"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_screen_hotkey_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.main._run_powershell",
        lambda *a, **k: {"stdout": "", "stderr": "", "code": 0},
    )
    r = client.post(
        "/screen/hotkey",
        json={"keys": ["ctrl", "s"]},
        headers={"X-Hostagent-Token": "secret"},
    )
    assert r.status_code == 200


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_screen_scroll_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.main._run_powershell",
        lambda *a, **k: {"stdout": "", "stderr": "", "code": 0},
    )
    r = client.post(
        "/screen/scroll",
        json={"clicks": -2},
        headers={"X-Hostagent-Token": "secret"},
    )
    assert r.status_code == 200
