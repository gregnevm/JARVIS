"""Тести PowerShell Panel /app/ps/*."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "webapp_dev_open", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    async def _fake_flags(_redis):
        return {
            "streaming": True,
            "voice_reply": False,
            "streaming_default": True,
            "voice_default": False,
        }

    monkeypatch.setattr("app.webapp.get_flags", _fake_flags)

    with TestClient(app) as c:
        tools = c.app.state.tools
        tools.get_ps_policy = AsyncMock(
            return_value={
                "enable_computer_use": True,
                "require_confirm": True,
                "hostagent_up": True,
                "ps_whitelist": ["get-service"],
                "learned_ps": [],
                "effective": ["get-service"],
            }
        )
        tools.get_ps_audit = AsyncMock(
            return_value={"entries": [{"tool": "run_powershell", "ts": 1}]}
        )
        tools.get_ps_pending = AsyncMock(return_value={"pending": False})
        tools.get_trust_status = AsyncMock(return_value={"trusted": False, "ttl_seconds": 0})
        tools.confirm_computer = AsyncMock(return_value=("ok\n[exit 0]", "origin text"))
        tools.cancel_computer = AsyncMock(return_value=None)

        async def _stream(_payload):
            yield {"tool_start": {"name": "run_powershell", "args": {"script": "Get-Service"}}}
            yield {"tool_done": {"name": "run_powershell", "result": "Running\n[exit 0]"}}
            yield {"done": True, "mode": "computer", "iters": 1, "text": "Готово"}

        tools.stream = _stream

        svc = c.app.state.svc
        svc.dashboard = AsyncMock(
            return_value={
                "hostagent_up": True,
                "enable_computer_use": True,
                "ollama_up": True,
            }
        )
        yield c


def test_ps_policy(client):
    r = client.get("/app/ps/policy")
    assert r.status_code == 200
    data = r.json()
    assert data["enable_computer_use"] is True
    assert "get-service" in data["effective"]


def test_ps_audit(client):
    r = client.get("/app/ps/audit?limit=10")
    assert r.status_code == 200
    assert r.json()["entries"][0]["tool"] == "run_powershell"


def test_ps_status(client):
    r = client.get("/app/ps/status")
    assert r.status_code == 200
    data = r.json()
    assert data["hostagent_up"] is True
    assert "trusted" in data


def test_ps_pending(client):
    r = client.get("/app/ps/pending")
    assert r.status_code == 200
    assert r.json()["pending"] is False


def test_ps_confirm(client):
    r = client.post("/app/ps/confirm", json={"code": "abc123"})
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    assert data["origin"] == "origin text"


def test_ps_cancel(client):
    r = client.post("/app/ps/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_ps_ask_sse(client):
    r = client.post("/app/ps/ask", json={"text": "покажи сервіси"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    chunks = []
    for line in r.text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            chunks.append(json.loads(line[5:].strip()))
    assert any("tool_start" in c for c in chunks)
    assert any("done" in c and c["done"] for c in chunks)
