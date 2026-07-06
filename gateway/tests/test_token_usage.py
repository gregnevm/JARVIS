"""SY-6: token-usage агрегатор зі стору + tokens-блок у /v1/usage (один SSOT)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from app.config import settings
from app.main import app
from app.saas import token_usage
from fastapi.testclient import TestClient


def _ev(days_ago: float, payload: dict[str, Any]) -> dict[str, Any]:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {"event_ts": ts.isoformat(), "payload": payload}


# --- чиста агрегація ---

def test_summarize_sums_and_merges_models():
    events = [
        _ev(0.1, {"calls": 2, "tokens_out": 10, "tokens_in": 4,
                  "by_model": {"m1": {"calls": 2, "tokens_out": 10, "tokens_in": 4}}}),
        _ev(0.2, {"calls": 1, "tokens_out": 5, "tokens_in": 1,
                  "by_model": {"m1": {"calls": 1, "tokens_out": 5, "tokens_in": 1}}}),
    ]
    out = token_usage.summarize_usage_events(events, days=7)
    assert out["calls"] == 3 and out["tokens_out"] == 15 and out["tokens_in"] == 5
    assert out["by_model"]["m1"]["calls"] == 3
    assert out["passports"] == 2


def test_summarize_filters_window_and_malformed():
    events = [
        _ev(30, {"calls": 9, "tokens_out": 999}),          # поза вікном — не рахується
        _ev(0.5, {"calls": 1, "tokens_out": 7}),
        {"event_ts": None, "payload": "not-a-dict"},        # малформед — скіп
    ]
    out = token_usage.summarize_usage_events(events, days=7)
    assert out["tokens_out"] == 7 and out["passports"] == 1


async def test_summary_graceful_when_memory_down(monkeypatch):
    from jarvis_core.service_client import ServiceError

    async def boom(*a: Any, **kw: Any) -> dict[str, Any]:
        raise ServiceError("memory", "POST", "/context/recent", detail="down")

    monkeypatch.setattr(token_usage, "call_dict", boom)
    out = await token_usage.token_usage_summary(days=7)
    assert out["error"] == "memory_unreachable"


async def test_summary_queries_usage_uid(monkeypatch):
    seen: dict[str, Any] = {}

    async def fake(base: str, method: str, path: str, **kw: Any) -> dict[str, Any]:
        seen["path"] = path
        seen["json"] = kw.get("json")
        return {"events": [_ev(0.1, {"calls": 1, "tokens_out": 3})]}

    monkeypatch.setattr(token_usage, "call_dict", fake)
    out = await token_usage.token_usage_summary(days=7)
    assert out["tokens_out"] == 3
    assert seen["path"] == "/context/recent"
    assert seen["json"]["user_id"] == settings.usage_meter_user_id
    assert seen["json"]["tags"] == ["kind:usage"]


# --- /v1/usage: tokens-блок з того самого SSOT ---

@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_api", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_default_user_id", 42)
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    with TestClient(app) as c:
        yield c


def test_v1_usage_includes_tokens_block(api_client, monkeypatch):
    class _FakeUsageStore:
        def __init__(self, *_a: Any) -> None: ...
        async def record(self, kid: str, endpoint: str) -> None: ...
        async def summary(self, kid: str, days: int = 7) -> dict[str, Any]:
            return {"object": "usage", "key_id": kid, "days": days, "total_requests": 5}

    async def fake_tokens(days: int = 7) -> dict[str, Any]:
        return {"object": "token_usage", "days": days, "tokens_out": 123}

    monkeypatch.setattr("app.openai_api._usage_store", lambda _req: _FakeUsageStore())
    monkeypatch.setattr("app.saas.token_usage.token_usage_summary", fake_tokens)
    r = api_client.get("/v1/usage", headers={"Authorization": "Bearer sk-test"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_requests"] == 5
    assert body["tokens"]["tokens_out"] == 123  # SSOT-блок зі стору поруч із requests
