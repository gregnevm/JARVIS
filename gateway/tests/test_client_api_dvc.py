"""Client-API: driver (remote PC) + chrome (extension queue) + code (dispatch)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = ("admin", "secret")


class FakeTools:
    async def process(self, payload):
        return "did: " + str(payload.get("text", "")) + " [" + str(payload.get("mode")) + "]"

    async def aclose(self):
        return None


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.kv = {}

    async def lpush(self, k, v):
        self.lists.setdefault(k, []).insert(0, v)

    async def rpop(self, k):
        lst = self.lists.get(k) or []
        return lst.pop() if lst else None

    async def expire(self, k, ttl):
        return True

    async def setex(self, k, ttl, v):
        self.kv[k] = v

    async def get(self, k):
        return self.kv.get(k)

    async def aclose(self):
        return None


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "")


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    with TestClient(app) as c:
        app.state.tools = FakeTools()
        app.state.redis = FakeRedis()
        yield c


# --- driver ---

def test_driver_exec_uses_computer_mode(client):
    r = client.post("/api/v1/driver/exec", auth=AUTH, json={"text": "відкрий блокнот"})
    assert r.status_code == 200
    assert "[computer]" in r.json()["reply"]


def test_driver_exec_requires_text(client):
    assert client.post("/api/v1/driver/exec", auth=AUTH, json={"text": " "}).status_code == 400


# --- chrome extension queue ---

def test_chrome_command_poll_result_cycle(client):
    # агент кладе команду
    cid = client.post("/api/v1/chrome/command", auth=AUTH,
                      json={"action": "navigate", "url": "https://example.com"}).json()["id"]
    # розширення опитує
    cmd = client.get("/api/v1/chrome/poll", auth=AUTH).json()
    assert cmd["action"] == "navigate" and cmd["url"] == "https://example.com" and cmd["id"] == cid
    # порожня черга
    assert client.get("/api/v1/chrome/poll", auth=AUTH).json() == {}
    # розширення повертає результат
    client.post("/api/v1/chrome/result", auth=AUTH, json={"id": cid, "ok": True, "result": "ok"})
    res = client.get(f"/api/v1/chrome/result/{cid}", auth=AUTH).json()
    assert res["status"] == "done" and res["result"] == "ok"


def test_chrome_result_pending(client):
    assert client.get("/api/v1/chrome/result/none", auth=AUTH).json()["status"] == "pending"


# --- code ---

def test_code_modes_lists_local(client):
    m = client.get("/api/v1/code/modes", auth=AUTH).json()
    assert m["local"]["available"] is True
    assert m["claude"]["available"] is False  # дефолт off (S1)


def test_code_task_dispatches_local(client):
    r = client.post("/api/v1/code/task", auth=AUTH, json={"text": "додай тест"})
    assert r.status_code == 200 and "[computer]" in r.json()["reply"]


def test_code_claude_disabled_503(client):
    r = client.post("/api/v1/code/task", auth=AUTH, json={"text": "x", "target": "claude"})
    assert r.status_code == 503


def test_dvc_requires_auth(client):
    assert client.post("/api/v1/driver/exec", json={"text": "x"}).status_code == 401
    assert client.get("/api/v1/chrome/poll").status_code == 401
