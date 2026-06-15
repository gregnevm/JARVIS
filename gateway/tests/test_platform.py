"""Тести Platform-консолі `/platform` (P0.9): auth, overview, workbench, memory, logs,
settings, users, models."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = ("admin", "secret")

_DASH = {
    "ollama_host": "http://127.0.0.1:9",
    "ollama_up": True,
    "chat_model": "qwen2.5:7b",
    "agent_model": "qwen2.5:14b",
    "vision_model": "llava",
    "embed_model": "nomic-embed",
    "agent_mode": "hybrid",
    "agent_mode_env": "hybrid",
    "metrics": {
        "turn_ms": {"count": 5, "p50_ms": 120, "p95_ms": 240, "avg_ms": 150},
        "rag_hit_rate": 0.5,
        "rag_queries": 10,
        "tools": {"web_search": {"count": 3, "p50_ms": 40, "p95_ms": 90}},
        "tok_s": {"count": 12, "p50": 42.5, "p95": 55.0, "avg": 40.0},
    },
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "memory_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)

    # Уникаємо мережі/redis в overview.
    async def _stack(_svc):
        return {"hostagent_up": True, "docker_up": True, "ollama_up": True}

    async def _probe():
        return [{"name": "tools", "ok": True, "status": 200, "ms": 3}]

    async def _prev(_r):
        return {}

    monkeypatch.setattr("app.platform.overview._fetch_stack", _stack)
    monkeypatch.setattr("app.platform.overview.probe_services", _probe)
    monkeypatch.setattr("app.platform.overview._safe_health_prev", _prev)

    async def _flags(_r):
        return {"streaming": True, "voice_reply": False, "streaming_default": True, "voice_default": False}

    async def _setflag(_r, _n, _e):
        return None

    monkeypatch.setattr("app.platform.settings_api.get_flags", _flags)
    monkeypatch.setattr("app.platform.settings_api.set_flag", _setflag)

    async def _exec_action(_a, _svc, _r):
        return "✅ rate-limit скинуто"

    monkeypatch.setattr("app.platform.users.execute_action", _exec_action)

    with TestClient(app) as c:
        svc = c.app.state.svc
        svc.dashboard = AsyncMock(return_value=_DASH)
        svc.twin_status = AsyncMock(return_value={"phase": "idle"})
        svc.twin_lora_versions = AsyncMock(return_value={"versions": ["lora-001", "lora-002"]})
        svc.twin_promote_lora = AsyncMock(
            return_value={"status": "ok", "ollama": {"ok": True, "model": "jarvis-lora:v2"}}
        )
        svc.twin_rollback_lora = AsyncMock(
            return_value={"status": "ok", "ollama": {"ok": True, "model": "jarvis-lora:v1"}}
        )
        svc.set_mode = AsyncMock(return_value={"mode": "agent", "status": "ok"})
        svc.reset_mode = AsyncMock(return_value={"mode": "hybrid", "status": "reset"})

        async def _stream(_payload):
            yield {"tool_start": {"name": "web_search", "args": {"query": "погода"}}}
            yield {"tool_done": {"name": "web_search", "result": "сонячно"}}
            yield {"delta": "Сьогодні "}
            yield {"delta": "сонячно."}
            yield {"done": True, "mode": "agent", "iters": 1, "text": "Сьогодні сонячно."}

        c.app.state.tools.stream = _stream
        c.app.state.tg.send_message = AsyncMock(return_value=None)
        yield c


# ---------------- auth ----------------
def test_requires_auth(client):
    assert client.get("/platform/api/overview").status_code == 401


def test_bad_credentials(client):
    assert client.get("/platform/api/overview", auth=("admin", "wrong")).status_code == 401


def test_whoami(client):
    r = client.get("/platform/api/whoami", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["via"] == "basic"
    assert data["user_id"] == 42


def test_spa_served(client):
    r = client.get("/platform")
    assert r.status_code == 200
    assert "JARVIS Platform" in r.text


# ---------------- overview ----------------
def test_overview(client):
    r = client.get("/platform/api/overview", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["metrics"]["turn_ms"]["p95_ms"] == 240
    assert d["metrics"]["tok_s"]["p50"] == 42.5
    assert d["models"]["chat_model"] == "qwen2.5:7b"
    assert d["stack"]["hostagent_up"]["ok"] is True
    assert d["agent_mode"] == "hybrid"


# ---------------- workbench ----------------
def test_workbench_sse(client):
    r = client.post("/platform/api/workbench/ask", auth=AUTH, json={"text": "яка погода", "mode": "agent"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    events = [json.loads(l[5:].strip()) for l in r.text.split("\n") if l.strip().startswith("data:")]
    assert any("tool_start" in e for e in events)
    assert any(e.get("done") for e in events)
    assert events[-1]["text"] == "Сьогодні сонячно."


def test_workbench_bad_mode(client):
    r = client.post("/platform/api/workbench/ask", auth=AUTH, json={"text": "hi", "mode": "nonsense"})
    assert r.status_code == 400


def test_workbench_empty_text(client):
    r = client.post("/platform/api/workbench/ask", auth=AUTH, json={"text": "  ", "mode": "auto"})
    assert r.status_code == 400


def test_workbench_confirm(client, monkeypatch):
    monkeypatch.setattr("app.auth.can_use_computer", lambda uid: True)
    client.app.state.tools.confirm_computer = AsyncMock(
        return_value=("ok output", "original question")
    )
    client.app.state.tools.get_ps_pending = AsyncMock(return_value={"pending": True, "code": "abc"})
    r = client.post("/platform/api/workbench/confirm", auth=AUTH, json={"code": "abc123"})
    assert r.status_code == 200
    assert r.json()["result"] == "ok output"


def test_workbench_cancel(client, monkeypatch):
    monkeypatch.setattr("app.auth.can_use_computer", lambda uid: True)
    client.app.state.tools.cancel_computer = AsyncMock(return_value=None)
    r = client.post("/platform/api/workbench/cancel", auth=AUTH, json={})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


# ---------------- memory ----------------
def test_memory_profile(client, tmp_path):
    pdir = tmp_path / "profiles"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "42.json").write_text(json.dumps({"language": "uk", "style": "стисло"}), encoding="utf-8")
    r = client.get("/platform/api/memory/profile", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is True
    assert d["user_id"] == 42
    assert d["profile"]["language"] == "uk"


def test_memory_profile_missing(client):
    r = client.get("/platform/api/memory/profile?user_id=999", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["exists"] is False


def test_memory_search_graceful(client):
    # memory_url недосяжний → 200 з порожнім результатом (не 5xx).
    r = client.post("/platform/api/memory/search", auth=AUTH, json={"query": "тест"})
    assert r.status_code == 200
    d = r.json()
    assert d["results"] == []
    assert d["user_id"] == 42


def test_memory_search_empty_query(client):
    r = client.post("/platform/api/memory/search", auth=AUTH, json={"query": ""})
    assert r.status_code == 400


def test_memory_search_project_id(client):
    r = client.post(
        "/platform/api/memory/search",
        auth=AUTH,
        json={"query": "тест", "project_id": 7},
    )
    assert r.status_code == 200
    assert r.json()["project_id"] == 7


def test_memory_notes(client, tmp_path):
    ndir = tmp_path / "notes"
    ndir.mkdir(parents=True, exist_ok=True)
    (ndir / "42.jsonl").write_text(
        json.dumps({"ts": 1700000000, "text": "купити молоко"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    r = client.get("/platform/api/memory/notes", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["user_id"] == 42
    assert len(d["notes"]) == 1
    assert d["notes"][0]["text"] == "купити молоко"


# ---------------- logs ----------------
def _write_log(tmp_path: Path) -> None:
    d = tmp_path / "logs" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    rows = [
        {"ts": 1000, "user_id": 42, "mode": "chat", "iters": 0, "user": "привіт", "assistant": "вітаю"},
        {"ts": 1001, "user_id": 42, "mode": "agent", "iters": 2, "user": "порахуй", "assistant": "42"},
    ]
    (d / "user_42.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_logs_users(client, tmp_path):
    _write_log(tmp_path)
    r = client.get("/platform/api/logs/users", auth=AUTH)
    assert r.status_code == 200
    users = r.json()["users"]
    assert users and users[0]["user_id"] == 42
    assert users[0]["turns"] == 2


def test_logs_tail(client, tmp_path):
    _write_log(tmp_path)
    r = client.get("/platform/api/logs?user_id=42&limit=10", auth=AUTH)
    assert r.status_code == 200
    turns = r.json()["turns"]
    assert len(turns) == 2
    assert turns[0]["ts"] == 1001  # новіші першими


def test_logs_mode_filter(client, tmp_path):
    _write_log(tmp_path)
    r = client.get("/platform/api/logs?user_id=42&mode=agent", auth=AUTH)
    assert r.status_code == 200
    turns = r.json()["turns"]
    assert len(turns) == 1
    assert turns[0]["mode"] == "agent"


# ---------------- settings ----------------
def test_settings_get(client):
    r = client.get("/platform/api/settings", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["flags"]["streaming"] is True
    assert "agent" in d["env"]
    assert d["agent_mode"] == "hybrid"


def test_settings_flag(client):
    r = client.post("/platform/api/settings/flag", auth=AUTH, json={"name": "streaming", "enabled": False})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_settings_bad_flag(client):
    r = client.post("/platform/api/settings/flag", auth=AUTH, json={"name": "hacking", "enabled": True})
    assert r.status_code == 400


def test_settings_mode(client):
    r = client.post("/platform/api/settings/mode", auth=AUTH, json={"mode": "agent"})
    assert r.status_code == 200
    assert r.json()["mode"] == "agent"


def test_settings_mode_reset(client):
    r = client.request("DELETE", "/platform/api/settings/mode", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "reset"


# ---------------- users ----------------
def test_users_list(client):
    r = client.get("/platform/api/users", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["pending"] == []
    assert 42 in d["admin_ids"]


def test_users_ratelimit_reset(client):
    r = client.post("/platform/api/users/ratelimit/reset", auth=AUTH, json={"user_id": 42})
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------- models ----------------
def test_models_get(client):
    r = client.get("/platform/api/models", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["mapping"]["chat"] == "qwen2.5:7b"
    assert d["tags"] == []  # ollama недосяжний → graceful


def test_models_lora(client):
    r = client.get("/platform/api/models/lora", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["versions"] == ["lora-001", "lora-002"]


def test_models_lora_promote(client):
    r = client.post("/platform/api/models/lora/promote", auth=AUTH, json={"version": "lora-002"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ollama"]["model"] == "jarvis-lora:v2"
