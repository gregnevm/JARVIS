"""Client-API context ingest/ретрив (CL-3, P9/P10) — /api/v1/ingest|context/*.

TestClient + Basic-auth (як test_client_api.py); memory-виклик (`_post_memory`)
мокаємо на рівні модуля — без мережі/БД. Перевіряємо прапор, auth, батч-лічильники,
org-scope (uid=legacy_uid), стелю батчу і graceful-фолбек при недоступному memory."""
from __future__ import annotations

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

from jarvis_core.service_client import ServiceError

AUTH = ("admin", "secret")


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "")


class _MemorySpy:
    """Записує (endpoint, payload) і віддає canned-відповіді; тест може override."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.responses: dict[str, object] = {
            "ingest": {"id": 1, "inserted": True},
            "search": {"results": [{"id": 1, "summary": "found"}]},
            "recent": {"events": [{"id": 1, "summary": "recent"}]},
            "purge": {"deleted": 5},
            "ledger": {"total": 7, "by_kind": {"note": 7}, "by_source": {}, "recent": []},
        }
        self.raise_on: set[str] = set()

    async def __call__(self, endpoint: str, payload: dict) -> dict:
        self.calls.append((endpoint, payload))
        if endpoint in self.raise_on:
            raise ServiceError("memory", "POST", f"/context/{endpoint}", detail="memory down")
        resp = self.responses[endpoint]
        return resp(payload) if callable(resp) else dict(resp)  # type: ignore[operator]


class _ToolsSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, path: str, params: dict) -> dict:
        self.calls.append((path, params))
        return {"job": path.rsplit("/", 1)[-1], "summarized": 1}


@pytest.fixture
def spy(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "enable_context_api", True)
    s = _MemorySpy()
    monkeypatch.setattr("app.client_api.context._post_memory", s)
    s.tools = _ToolsSpy()  # type: ignore[attr-defined]
    monkeypatch.setattr("app.client_api.context._post_tools", s.tools)
    return s


@pytest.fixture
def client(spy):
    with TestClient(app) as c:
        yield c


# --- прапор / auth ---

def test_ingest_disabled_returns_404(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "enable_context_api", False)
    with TestClient(app) as c:
        r = c.post("/api/v1/ingest/events", auth=AUTH,
                   json={"events": [{"summary": "x"}]})
    assert r.status_code == 404


def test_ingest_requires_auth(client):
    r = client.post("/api/v1/ingest/events", json={"events": [{"summary": "x"}]})
    assert r.status_code == 401


# --- ingest батч ---

def test_ingest_counts_accepted_and_duplicates(client, spy):
    def resp(payload):
        # дубль, якщо event_id == "dup"
        return {"id": 9, "inserted": payload.get("event_id") != "dup"}
    spy.responses["ingest"] = resp
    r = client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [
            {"summary": "новий", "event_id": "a"},
            {"summary": "повтор", "event_id": "dup"},
        ]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 1
    assert body["failed"] == 0


def test_ingest_forwards_org_scope_and_passport(client, spy):
    client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"kind": "note", "summary": "купив молоко",
                          "tags": ["topic:groceries"]}]},
    )
    endpoint, payload = spy.calls[-1]
    assert endpoint == "ingest"
    assert payload["user_id"] == 42                      # legacy_uid (Basic→admin 42)
    assert payload["org_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["kind"] == "note"
    # gateway будує фінішний паспорт: теги нормалізовані (kind-тег першим, P10)
    assert payload["tags"][0] == "kind:note"
    assert "topic:groceries" in payload["tags"]


def test_ingest_redacts_secrets_before_forwarding(client, spy):
    """Серверна редакція: картка/OTP не долітають до memory у відкритому вигляді."""
    client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"kind": "sms", "summary": "картка 4111 1111 1111 1111, код 482913"}]},
    )
    sent = spy.calls[-1][1]["summary"]
    assert "[REDACTED:card]" in sent
    assert "[REDACTED:otp]" in sent
    assert "4111" not in sent and "482913" not in sent


def test_ingest_health_drops_raw_payload(client, spy):
    client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"kind": "note", "summary": "візит", "sensitivity": "health",
                          "payload": {"raw": "діагноз X"}}]},
    )
    assert spy.calls[-1][1]["payload"] == {}  # health → сире не зберігаємо


def test_ingest_raw_path_marks_pending_and_keeps_raw(client, spy):
    """Подія лише з content → провізорний summary + тег pending:summary + raw у payload."""
    client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"kind": "worklog", "content": "довгий сирий текст без summary"}]},
    )
    payload = spy.calls[-1][1]
    assert "pending:summary" in payload["tags"]
    assert payload["summary"].startswith("довгий сирий текст")
    assert payload["payload"]["raw"] == "довгий сирий текст без summary"


def test_ingest_empty_event_counts_failed_not_sent(client, spy):
    r = client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"kind": "note"}]},  # ні summary, ні content
    )
    assert r.json()["failed"] == 1
    assert spy.calls == []  # порожню подію не шлемо в memory


def test_ingest_empty_batch_is_noop(client, spy):
    r = client.post("/api/v1/ingest/events", auth=AUTH, json={"events": []})
    assert r.json() == {"accepted": 0, "duplicates": 0, "failed": 0, "ids": []}
    assert spy.calls == []


def test_ingest_batch_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(settings, "context_ingest_max_batch", 2)
    r = client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"summary": str(i)} for i in range(3)]},
    )
    assert r.status_code == 413


def test_ingest_counts_failed_event_without_aborting_batch(client, spy):
    spy.raise_on = {"ingest"}
    r = client.post(
        "/api/v1/ingest/events",
        auth=AUTH,
        json={"events": [{"summary": "a"}, {"summary": "b"}]},
    )
    assert r.status_code == 200
    assert r.json()["failed"] == 2


# --- search / recent / purge ---

def test_search_returns_results(client, spy):
    r = client.post("/api/v1/context/search", auth=AUTH, json={"query": "молоко"})
    assert r.status_code == 200
    assert r.json()["results"][0]["summary"] == "found"
    assert spy.calls[-1][1]["user_id"] == 42


def test_search_graceful_when_memory_down(client, spy):
    spy.raise_on = {"search"}
    r = client.post("/api/v1/context/search", auth=AUTH, json={"query": "x"})
    assert r.status_code == 200
    assert r.json() == {"results": [], "error": "memory_unreachable"}


def test_recent_returns_events(client):
    r = client.post("/api/v1/context/recent", auth=AUTH, json={"limit": 5, "kind": "daily"})
    assert r.status_code == 200
    assert r.json()["events"][0]["summary"] == "recent"


def test_purge_returns_deleted(client):
    r = client.post("/api/v1/context/purge", auth=AUTH, json={"kind": "sms"})
    assert r.json()["deleted"] == 5


def test_purge_502_when_memory_down(client, spy):
    spy.raise_on = {"purge"}
    r = client.post("/api/v1/context/purge", auth=AUTH, json={})
    assert r.status_code == 502


# --- context-jobs proxy (тригер у tools) ---

def test_job_proxies_to_tools_with_uid(client, spy):
    r = client.post("/api/v1/context/jobs/context_daily", auth=AUTH)
    assert r.status_code == 200
    path, params = spy.tools.calls[-1]
    assert path == "/context/jobs/context_daily"
    assert params["user_id"] == 42


def test_job_unknown_name_404(client):
    r = client.post("/api/v1/context/jobs/bogus", auth=AUTH)
    assert r.status_code == 404


def test_job_requires_auth(client):
    assert client.post("/api/v1/context/jobs/context_daily").status_code == 401


def test_job_disabled_404(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "enable_context_api", False)
    with TestClient(app) as c:
        assert c.post("/api/v1/context/jobs/context_daily", auth=AUTH).status_code == 404


def test_ledger_returns_aggregates(client, spy):
    r = client.post("/api/v1/context/ledger", auth=AUTH, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 7 and body["by_kind"]["note"] == 7
    assert spy.calls[-1][1]["user_id"] == 42
