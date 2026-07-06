"""SY-5 MVP: confirm-запит → push + паспорти confirm_request/confirm_decision."""
from __future__ import annotations

from typing import Any

import pytest
from app import computer_confirm, confirm_events, context_emit
from app.config import settings


class _IngestSpy:
    def __init__(self) -> None:
        self.stores: list[dict[str, Any]] = []

    async def context_ingest(self, store: dict[str, Any]) -> dict[str, Any]:
        self.stores.append(store)
        return {"inserted": True}


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, val: str) -> None:
        self.store[key] = val

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture
def env(monkeypatch):
    spy = _IngestSpy()
    pushes: list[dict[str, Any]] = []

    async def fake_push(**kw: Any) -> bool:
        pushes.append(kw)
        return True

    monkeypatch.setattr(context_emit, "_memory", spy)
    monkeypatch.setattr(confirm_events, "publish_ntfy", fake_push)
    monkeypatch.setattr(settings, "enable_confirm_push", True)
    monkeypatch.setattr(settings, "push_enabled", True)
    monkeypatch.setattr(settings, "ntfy_topic", "jarvis-test")
    monkeypatch.setattr(settings, "confirm_push_click_url", "https://app.example/app")
    return spy, pushes


async def _settle() -> None:
    await context_emit.drain()
    await confirm_events.drain()


# --- прапор ---

async def test_flag_off_is_silent(monkeypatch):
    spy = _IngestSpy()
    monkeypatch.setattr(context_emit, "_memory", spy)
    monkeypatch.setattr(settings, "enable_confirm_push", False)
    confirm_events.notify_confirm_request(7, "abc123", tool="fs_write", description="d", tier="T0")
    confirm_events.emit_confirm_decision(7, "abc123", confirm_events.DECISION_APPROVED)
    await _settle()
    assert spy.stores == []


# --- конверти (SY-5.2) ---

async def test_request_passport_and_push(env):
    spy, pushes = env
    confirm_events.notify_confirm_request(
        7, "abc123", tool="fs_write", description="Запис у файл x.txt", tier="T0"
    )
    await _settle()
    st = spy.stores[0]
    assert st["kind"] == "confirm_request" and st["user_id"] == 7
    assert {"priority:high", "module:computer", "tool:fs_write", "tier:t0"} <= set(st["tags"])
    assert st["ref"] == "confirm:abc123" and st["payload"]["code"] == "abc123"
    assert len(pushes) == 1
    p = pushes[0]
    assert "abc123" in p["message"] and "Запис у файл" in p["message"]
    assert p["click"] == "https://app.example/app"
    assert p["topic"] == "jarvis-test"


async def test_decision_passport(env):
    spy, _ = env
    confirm_events.emit_confirm_decision(
        7, "abc123", confirm_events.DECISION_APPROVED, tool="fs_write"
    )
    await _settle()
    st = spy.stores[0]
    assert st["kind"] == "confirm_decision"
    assert "status:approved" in st["tags"] and st["ref"] == "confirm:abc123"


# --- інтеграція: wrap_execute видає pending і шле запит ---

async def test_wrap_execute_emits_request(env, monkeypatch):
    spy, pushes = env
    fr = _FakeRedis()
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fr)
    monkeypatch.setattr("app.computer_rate_limit.get_redis", lambda: fr)
    monkeypatch.setattr("app.computer_trust.get_redis", lambda: fr)
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "7")
    monkeypatch.setattr(settings, "computer_require_confirm", True)
    monkeypatch.setattr(settings, "bypass_confirmations", False)

    async def never() -> str:
        raise AssertionError("не мало виконатись без confirm")

    out = await computer_confirm.wrap_execute(7, "fs_write", {"path": "x", "content": "y"}, never)
    assert "[[COMPUTER_CONFIRM:" in out
    await _settle()
    kinds = [s["kind"] for s in spy.stores]
    assert kinds == ["confirm_request"]
    assert len(pushes) == 1


# --- інтеграція: cancel_pending пише рішення cancelled ---

async def test_cancel_pending_emits_cancelled_decision(env, monkeypatch):
    spy, _ = env
    fr = _FakeRedis()
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fr)
    code = await computer_confirm.save_pending(7, "fs_write", {"path": "x"})
    await computer_confirm.cancel_pending(7)
    await _settle()
    decisions = [s for s in spy.stores if s["kind"] == "confirm_decision"]
    assert len(decisions) == 1
    assert decisions[0]["payload"]["decision"] == "cancelled"
    assert decisions[0]["payload"]["code"] == code
    assert (await computer_confirm.load_pending_raw(7)) == {"pending": False}


async def test_cancel_without_pending_is_silent(env, monkeypatch):
    spy, _ = env
    fr = _FakeRedis()
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fr)
    await computer_confirm.cancel_pending(7)
    await _settle()
    assert spy.stores == []
