"""Тести Platform Projects API (P1): CRUD-проксі до memory + активний проєкт."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = ("admin", "secret")


def _resp(status: int, payload: dict) -> dict:
    """Новий контракт _mem (R2): 2xx -> dict, 4xx/5xx -> HTTPException (bubble)."""
    if status >= 400:
        raise HTTPException(status_code=status, detail=payload.get("detail", "memory error"))
    return payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)

    active: dict[int, int] = {}

    async def fake_get_active(_redis, uid):
        return active.get(int(uid))

    async def fake_set_active(_redis, uid, pid):
        if pid is None:
            active.pop(int(uid), None)
        else:
            active[int(uid)] = int(pid)

    monkeypatch.setattr("app.platform.projects.get_active", fake_get_active)
    monkeypatch.setattr("app.platform.projects.set_active", fake_set_active)

    store: dict[int, dict] = {
        1: {"id": 1, "user_id": 42, "name": "Робота", "system_prompt": "стисло",
            "archived": False, "updated_at": ""},
    }

    async def fake_mem(method, path, **kw):
        parts = path.strip("/").split("/")
        if path == "/projects" and method == "GET":
            return _resp(200, {"projects": list(store.values())})
        if path == "/projects" and method == "POST":
            pid = (max(store) + 1) if store else 1
            store[pid] = {"id": pid, "user_id": 42, "name": kw["json"]["name"],
                          "system_prompt": kw["json"].get("system_prompt", ""),
                          "archived": False, "updated_at": ""}
            return _resp(200, store[pid])
        if parts[:1] == ["projects"] and len(parts) == 2:
            pid = int(parts[1])
            if method == "GET":
                return _resp(200, {**store[pid], "files": []}) if pid in store else _resp(404, {"detail": "not found"})
            if method == "PATCH":
                if pid not in store:
                    return _resp(404, {"detail": "not found"})
                store[pid].update({k: v for k, v in kw["json"].items() if k != "user_id"})
                return _resp(200, store[pid])
            if method == "DELETE":
                if pid not in store:
                    return _resp(404, {"detail": "not found"})
                del store[pid]
                return _resp(200, {"ok": True})
        if "files" in parts:
            return _resp(200, {"id": 7, "name": (kw.get("json") or {}).get("name", "f")})
        return _resp(404, {"detail": "unknown"})

    monkeypatch.setattr("app.platform.projects._mem", fake_mem)

    with TestClient(app) as c:
        yield c


def test_requires_auth(client):
    assert client.get("/platform/api/projects").status_code == 401


def test_projects_list(client):
    r = client.get("/platform/api/projects?include_archived=true", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["active_id"] is None
    assert d["projects"][0]["name"] == "Робота"


def test_projects_create(client):
    r = client.post("/platform/api/projects", auth=AUTH, json={"name": "Навчання"})
    assert r.status_code == 200
    assert r.json()["name"] == "Навчання"


def test_projects_create_empty(client):
    assert client.post("/platform/api/projects", auth=AUTH, json={"name": "  "}).status_code == 400


def test_active_set_get(client):
    assert client.post("/platform/api/projects/active", auth=AUTH, json={"project_id": 1}).status_code == 200
    r = client.get("/platform/api/projects/active", auth=AUTH)
    assert r.json()["active_id"] == 1


def test_active_set_missing(client):
    r = client.post("/platform/api/projects/active", auth=AUTH, json={"project_id": 999})
    assert r.status_code == 404


def test_active_clear(client):
    client.post("/platform/api/projects/active", auth=AUTH, json={"project_id": 1})
    client.post("/platform/api/projects/active", auth=AUTH, json={"project_id": None})
    assert client.get("/platform/api/projects/active", auth=AUTH).json()["active_id"] is None


def test_delete_clears_active(client):
    client.post("/platform/api/projects/active", auth=AUTH, json={"project_id": 1})
    assert client.delete("/platform/api/projects/1", auth=AUTH).status_code == 200
    assert client.get("/platform/api/projects/active", auth=AUTH).json()["active_id"] is None


def test_project_get_404(client):
    assert client.get("/platform/api/projects/999", auth=AUTH).status_code == 404


def test_project_update(client):
    r = client.patch("/platform/api/projects/1", auth=AUTH, json={"system_prompt": "детально"})
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "детально"


def test_project_file_add(client):
    r = client.post("/platform/api/projects/1/files", auth=AUTH, json={"name": "spec.md", "content": "x"})
    assert r.status_code == 200
    assert r.json()["name"] == "spec.md"
