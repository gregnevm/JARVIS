"""Client-API workspace: chats (sessions/history) + projects CRUD проксі."""
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


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    calls = {}

    async def fake_get(path, params):
        calls["get"] = (path, params)
        if path == "/sessions":
            return {"sessions": [{"session_id": 1, "preview": "hi"}]}
        if path == "/projects":
            return {"projects": [{"id": 5, "name": "Робота"}]}
        if path.startswith("/projects/"):
            return {"id": 5, "name": "Робота", "files": []}
        return {}

    async def fake_mem(method, path, payload=None, params=None):
        calls["mem"] = (method, path, payload, params)
        if path == "/history":
            return {"messages": [{"role": "user", "content": "hi"}]}
        if path == "/projects":
            return {"id": 7, "name": payload["name"]}
        if method == "DELETE":
            return {"ok": True}
        return {"id": 5, "name": "renamed"}

    monkeypatch.setattr("app.client_api.workspace._mem_get", fake_get)
    monkeypatch.setattr("app.client_api.workspace._mem", fake_mem)
    with TestClient(app) as c:
        c._calls = calls  # type: ignore[attr-defined]
        yield c


def test_sessions_list(client):
    r = client.get("/api/v1/sessions", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["sessions"][0]["session_id"] == 1
    assert client._calls["get"][1]["user_id"] == 42


def test_history(client):
    r = client.post("/api/v1/history", auth=AUTH, json={"limit": 10})
    assert r.json()["messages"][0]["content"] == "hi"


def test_projects_list(client):
    r = client.get("/api/v1/projects", auth=AUTH)
    assert r.json()["projects"][0]["name"] == "Робота"


def test_projects_create(client):
    r = client.post("/api/v1/projects", auth=AUTH, json={"name": "Новий"})
    assert r.json()["name"] == "Новий"
    assert client._calls["mem"][2]["user_id"] == 42


def test_projects_get(client):
    r = client.get("/api/v1/projects/5", auth=AUTH)
    assert r.json()["id"] == 5


def test_projects_delete(client):
    r = client.delete("/api/v1/projects/5", auth=AUTH)
    assert r.json()["ok"] is True


def test_requires_auth(client):
    assert client.get("/api/v1/sessions").status_code == 401
