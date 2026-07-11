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
    # Регресія: wheel-дельта `dwData` для MOUSEEVENTF_WHEEL — ЗНАКОВА. Раніше
    # P/Invoke оголошував її `uint`, тож scroll-down (від'ємна дельта) кидав на
    # bind-і → /screen/scroll віддавав 500. Пінимо ТОЧНУ сигнатуру (не підрядок
    # "int d," — він є і в "uint d,").
    assert "uint dy, int d, uint e)" in ps       # wheel-параметр знаковий
    assert "uint dy, uint d, uint e)" not in ps  # жодної uint-сигнатури не лишилось


@pytest.mark.skipif(sys.platform != "win32", reason="windows only")
def test_scroll_down_pinvoke_binds_negative_delta():
    # Доводить фікс на реальній платформі: генерований PS Add-Type-ить сигнатуру
    # й біндить від'ємну дельту з flags=0 (безпечний no-op — біт WHEEL не
    # виставлений, події колеса не буде). До фіксу (`uint d`) це кидало
    # "Cannot convert ... -120 ... to System.UInt32"; після — exit 0.
    import subprocess

    snippet = build_scroll_ps(-1).replace(
        "[WinMouse]::mouse_event(0x0800, 0, 0, -120, 0)",
        "[WinMouse]::mouse_event(0, 0, 0, -120, 0)",  # flags=0 → no-op біндинг
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", snippet],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"negative wheel delta failed to bind: {r.stderr}"


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
