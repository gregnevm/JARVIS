"""Client-API: нативний voice (C2) + computer-confirm міст (BE5/CL-3.5)."""
from __future__ import annotations

import pytest
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


class FakeStt:
    async def transcribe(self, audio, filename="voice.m4a"):
        return "привіт джарвіс"

    async def aclose(self):
        return None


class FakeTools:
    async def process(self, payload):
        return "вітаю, " + str(payload.get("text", ""))

    async def aclose(self):
        return None


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    with TestClient(app) as c:
        app.state.stt = FakeStt()
        app.state.tools = FakeTools()
        yield c


# --- voice ---

def test_voice_transcribes_and_runs_agent(client):
    r = client.post("/api/v1/voice", auth=AUTH, content=b"\x00\x01audio")
    assert r.status_code == 200
    d = r.json()
    assert d["transcript"] == "привіт джарвіс"
    assert "вітаю" in d["reply"]


def test_voice_empty_body_400(client):
    assert client.post("/api/v1/voice", auth=AUTH, content=b"").status_code == 400


def test_voice_requires_auth(client):
    assert client.post("/api/v1/voice", content=b"x").status_code == 401


# --- confirm bridge ---

def test_confirm_pending_proxies(client, monkeypatch):
    async def fake_get(path, params):
        assert path == "/computer/pending"
        assert params["user_id"] == 42
        return {"pending": True, "action": "fs_write /tmp/x"}
    monkeypatch.setattr("app.client_api.confirm._tools_get", fake_get)
    r = client.get("/api/v1/confirm/pending", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["pending"] is True


def test_confirm_approve_proxies_code(client, monkeypatch):
    seen = {}
    async def fake_post(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return {"status": "executed"}
    monkeypatch.setattr("app.client_api.confirm._tools_post", fake_post)
    r = client.post("/api/v1/confirm/approve", auth=AUTH, json={"code": "1234"})
    assert r.status_code == 200
    assert seen["path"] == "/computer/confirm"
    assert seen["payload"] == {"user_id": 42, "code": "1234"}


def test_confirm_approve_requires_code(client):
    assert client.post("/api/v1/confirm/approve", auth=AUTH, json={"code": " "}).status_code == 400


def test_confirm_pending_graceful_when_tools_down(client, monkeypatch):
    from jarvis_core.service_client import ServiceError

    async def boom(path, params):
        raise ServiceError("tools", "GET", path, detail="down")
    monkeypatch.setattr("app.client_api.confirm._tools_get", boom)
    r = client.get("/api/v1/confirm/pending", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["pending"] is False
