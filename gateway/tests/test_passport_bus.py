"""SY-B1 wiring: ingest → emit ПІСЛЯ store → підписник (e2e DoD).

Прапор off → нуль змін поведінки; збій підписника не валить ingest; дублі не
емітяться; push-підписник ловить `priority:high`. Memory мокаємо як у
test_client_api_context.py (без мережі/БД).
"""
from __future__ import annotations

import time
from typing import Any, Callable

import pytest
from app import bus as gwbus
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

AUTH = ("admin", "secret")


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(settings, "enable_context_api", True)


class _MemoryStub:
    def __init__(self, inserted: bool = True) -> None:
        self.inserted = inserted

    async def __call__(self, endpoint: str, payload: dict) -> dict:
        return {"id": 9, "inserted": self.inserted}


@pytest.fixture
def bus_env(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "enable_passport_bus", True)
    monkeypatch.setattr("app.client_api.context._post_memory", _MemoryStub())
    gwbus.reset_passport_bus()
    yield
    gwbus.reset_passport_bus()


def _wait_for(cond: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Доставка fire-and-forget у loop-і TestClient — полінг із дедлайном."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _post_event(client: TestClient, event: dict[str, Any]):
    return client.post("/api/v1/ingest/events", auth=AUTH, json={"events": [event]})


# --- DoD: ingest → підписник отримав паспорт ---

def test_ingest_emits_passport_to_subscriber(bus_env):
    got: list[tuple] = []

    async def handler(passport, meta) -> None:
        got.append((passport, meta))

    gwbus.get_passport_bus().subscribe(["kind:invoice"], handler, name="spy")
    with TestClient(app) as c:
        r = _post_event(c, {"kind": "invoice", "summary": "рахунок", "tags": ["entity:acme"]})
        assert r.status_code == 200 and r.json()["accepted"] == 1
        assert _wait_for(lambda: len(got) == 1), "підписник не отримав паспорт"
    passport, meta = got[0]
    assert passport.kind == "invoice"
    assert passport.tags[0] == "kind:invoice" and "entity:acme" in passport.tags
    assert meta.user_id == 42 and meta.store_id == 9  # партиція — у BusMeta


def test_flag_off_means_zero_behavior_change(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "enable_passport_bus", False)
    monkeypatch.setattr("app.client_api.context._post_memory", _MemoryStub())
    gwbus.reset_passport_bus()
    got: list = []

    async def handler(passport, meta) -> None:
        got.append(passport)

    gwbus.get_passport_bus().subscribe([], handler, name="spy")
    with TestClient(app) as c:
        r = _post_event(c, {"summary": "тихо"})
        assert r.status_code == 200 and r.json()["accepted"] == 1
        time.sleep(0.05)
    assert got == []
    gwbus.reset_passport_bus()


def test_failing_subscriber_does_not_break_ingest(bus_env):
    async def boom(passport, meta) -> None:
        raise RuntimeError("підписник впав")

    gwbus.get_passport_bus().subscribe([], boom, name="boom")
    with TestClient(app) as c:
        r = _post_event(c, {"summary": "критична подія"})
        assert r.status_code == 200
        assert r.json() == {"accepted": 1, "duplicates": 0, "failed": 0, "ids": [9]}


def test_duplicate_is_not_emitted(bus_env, monkeypatch):
    """Ідемпотентність store = ідемпотентність шини: inserted=false → без emit."""
    monkeypatch.setattr(
        "app.client_api.context._post_memory", _MemoryStub(inserted=False)
    )
    got: list = []

    async def handler(passport, meta) -> None:
        got.append(passport)

    gwbus.get_passport_bus().subscribe([], handler, name="spy")
    with TestClient(app) as c:
        r = _post_event(c, {"summary": "повтор", "event_id": "dup"})
        assert r.json()["duplicates"] == 1
        time.sleep(0.05)
    assert got == []


# --- SY-B1.3: перший підписник — push (ntfy) на priority:high ---

def test_push_subscriber_fires_on_priority_high_only(bus_env, monkeypatch):
    calls: list[dict] = []

    async def fake_push(**kw) -> bool:
        calls.append(kw)
        return True

    monkeypatch.setattr("app.bus.publish_ntfy", fake_push)
    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_topic", "jarvis-test")
    with TestClient(app) as c:
        _post_event(c, {"kind": "note", "summary": "буденне"})  # без priority — тиша
        _post_event(
            c,
            {"kind": "reminder", "summary": "подзвонити мамі", "tags": ["priority:high"]},
        )
        assert _wait_for(lambda: len(calls) == 1), "push-підписник не спрацював"
        time.sleep(0.05)  # даємо шанс зайвим доставкам проявитись
    assert len(calls) == 1
    assert calls[0]["message"] == "подзвонити мамі"
    assert calls[0]["topic"] == "jarvis-test"
    assert calls[0]["title"].startswith("JARVIS")
