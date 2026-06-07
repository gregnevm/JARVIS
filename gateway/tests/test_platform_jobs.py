"""Platform Jobs API (P2)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = ("admin", "secret")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)

    with TestClient(app) as c:
        tools = c.app.state.tools
        tools.list_bg_jobs = AsyncMock(return_value=[{"id": "abc", "status": "done", "progress": 100}])
        tools.create_bg_job = AsyncMock(return_value={"id": "new1", "status": "queued"})
        tools.get_bg_job = AsyncMock(return_value={"id": "abc", "status": "running"})
        tools.cancel_bg_job = AsyncMock(return_value=True)
        yield c


def test_jobs_list(client):
    r = client.get("/platform/api/jobs", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["jobs"][0]["id"] == "abc"


def test_jobs_create(client):
    r = client.post("/platform/api/jobs", auth=AUTH, json={"text": "research topic", "mode": "agent"})
    assert r.status_code == 200
    assert r.json()["id"] == "new1"


def test_jobs_create_research(client):
    client.app.state.tools.create_research_job = AsyncMock(
        return_value={"id": "r1", "type": "deep_research", "status": "queued"}
    )
    r = client.post(
        "/platform/api/jobs",
        auth=AUTH,
        json={"text": "AI trends", "job_type": "deep_research"},
    )
    assert r.status_code == 200
    assert r.json()["type"] == "deep_research"


def test_jobs_create_empty(client):
    r = client.post("/platform/api/jobs", auth=AUTH, json={"text": "  "})
    assert r.status_code == 400


def test_jobs_get(client):
    r = client.get("/platform/api/jobs/abc", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_jobs_cancel(client):
    r = client.request("DELETE", "/platform/api/jobs/abc", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True
