"""Context Passport маршрути (P9/P10, C1) — /context/ingest|search|recent|purge.

Той самий підхід, що `test_main_routes.py`: підміняємо `app.state.db`/`embedder`
напряму й ходимо крізь ASGI без lifespan (без мережі/БД). Тут окремий FakeDB із
context-методами — щоб не роздувати спільний FakeDB і тримати тести фокусними."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from app.main import app


class FakeContextDB:
    def __init__(self) -> None:
        self.health = AsyncMock(return_value=True)
        self.add_context_event = AsyncMock(return_value={"id": 42, "inserted": True})
        self.search_context = AsyncMock(
            return_value=[{"id": 1, "summary": "found", "tags": ["kind:note"], "score": 0.9}]
        )
        self.recent_context = AsyncMock(
            return_value=[{"id": 1, "summary": "recent", "tags": ["kind:note"]}]
        )
        self.purge_context = AsyncMock(return_value=7)
        self.pending_context = AsyncMock(
            return_value=[{"id": 5, "summary": "excerpt", "tags": ["pending:summary"],
                           "payload": {"raw": "сирий"}}]
        )
        self.update_context_event = AsyncMock(return_value=True)
        self.context_ledger = AsyncMock(
            return_value={"total": 3, "by_kind": {"note": 2, "sms": 1},
                          "by_source": {"cli": 3}, "recent": []}
        )


class FakeEmbedder:
    def __init__(self) -> None:
        self.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def client():
    app.state.db = FakeContextDB()
    app.state.embedder = FakeEmbedder()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# --- /context/ingest ---

async def test_ingest_success_embeds_and_tags(client):
    async with client as c:
        r = await c.post(
            "/context/ingest",
            json={"user_id": 1, "kind": "note", "summary": "купив молоко"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] is True
    assert body["embedded"] is True
    assert body["tags"][0] == "kind:note"  # P10-інваріант: kind-тег гарантований
    # embedding передано в DB (не None)
    call = app.state.db.add_context_event.await_args
    assert call.kwargs["embedding"] == [0.1, 0.2, 0.3]


async def test_ingest_requires_summary_or_content(client):
    async with client as c:
        r = await c.post("/context/ingest", json={"user_id": 1, "summary": "   "})
    assert r.status_code == 400
    assert "summary or content" in r.json()["detail"]
    app.state.db.add_context_event.assert_not_awaited()


async def test_ingest_falls_back_to_content_for_summary(client):
    async with client as c:
        r = await c.post(
            "/context/ingest", json={"user_id": 1, "kind": "sms", "content": "текст смс"}
        )
    assert r.status_code == 200
    call = app.state.db.add_context_event.await_args
    assert call.kwargs["summary"] == "текст смс"


async def test_ingest_redacts_secrets_in_summary_and_payload(client):
    """P2-4: серверний backstop редакції — секрети не лягають у context_events."""
    secret = "sk-jarvis-ABCDEF0123456789ABCDEF0123456789"
    async with client as c:
        r = await c.post(
            "/context/ingest",
            json={
                "user_id": 1,
                "summary": f"токен {secret} і картка 4111 1111 1111 1111",
                "sensitivity": "personal",
                "payload": {"raw": f"key={secret}"},
            },
        )
    assert r.status_code == 200
    call = app.state.db.add_context_event.await_args
    assert secret not in call.kwargs["summary"]
    assert "[REDACTED:card]" in call.kwargs["summary"]
    assert secret not in call.kwargs["payload"]["raw"]


async def test_ingest_redacts_secrets_in_nested_payload(client):
    """Regression: плоский comprehension пропускав секрети у ВКЛАДЕНИХ dict/list
    payload → cleartext-leak у context_events попри C1-backstop. Тепер рекурсія."""
    secret = "sk-jarvis-ABCDEF0123456789ABCDEF0123456789"
    card = "4111 1111 1111 1111"
    async with client as c:
        r = await c.post(
            "/context/ingest",
            json={
                "user_id": 1,
                "summary": "нотатка",
                "sensitivity": "personal",
                "payload": {
                    "meta": {"token": f"key={secret}", "n": 7},
                    "cards": [card, {"deep": secret}],
                },
            },
        )
    assert r.status_code == 200
    payload = app.state.db.add_context_event.await_args.kwargs["payload"]
    assert secret not in str(payload)  # ніде на будь-якій глибині
    assert "[REDACTED:card]" in payload["cards"][0]
    assert payload["cards"][1]["deep"] == "[REDACTED:secret]"
    assert payload["meta"]["n"] == 7  # не-рядки недоторкані


async def test_ingest_drops_raw_payload_for_health(client):
    """Route-рівень: health/finance → сирий payload взагалі не персиститься
    ({}), незалежно від редакції значень (should_store_raw гейт до редакції)."""
    async with client as c:
        r = await c.post(
            "/context/ingest",
            json={
                "user_id": 1,
                "summary": "візит до лікаря",
                "sensitivity": "health",
                "payload": {"diagnosis": "секретний діагноз", "n": 3},
            },
        )
    assert r.status_code == 200
    assert app.state.db.add_context_event.await_args.kwargs["payload"] == {}


async def test_ingest_survives_embed_failure(client):
    """P1 offline-first: збір не падає, якщо Ollama недоступний — embedding=None."""
    app.state.embedder.embed = AsyncMock(side_effect=RuntimeError("ollama down"))
    async with client as c:
        r = await c.post("/context/ingest", json={"user_id": 1, "summary": "подія"})
    assert r.status_code == 200
    body = r.json()
    assert body["embedded"] is False
    assert body["inserted"] is True
    assert app.state.db.add_context_event.await_args.kwargs["embedding"] is None


async def test_ingest_normalizes_tags(client):
    async with client as c:
        await c.post(
            "/context/ingest",
            json={
                "user_id": 1,
                "kind": "call",
                "summary": "дзвінок мамі",
                "tags": ["Person:Mom", "person:mom", "  TOPIC:rent  "],
            },
        )
    tags = app.state.db.add_context_event.await_args.kwargs["tags"]
    assert tags[0] == "kind:call"           # kind-тег попереду
    assert "person:mom" in tags             # lowercased + дедуп
    assert tags.count("person:mom") == 1
    assert "topic:rent" in tags             # trimmed + lowercased


async def test_ingest_idempotent_duplicate_reports_not_inserted(client):
    app.state.db.add_context_event = AsyncMock(return_value={"id": 42, "inserted": False})
    async with client as c:
        r = await c.post(
            "/context/ingest",
            json={"user_id": 1, "summary": "подія", "event_id": "evt-1"},
        )
    assert r.json()["inserted"] is False


# --- /context/search ---

async def test_search_returns_results(client):
    async with client as c:
        r = await c.post("/context/search", json={"user_id": 1, "query": "молоко"})
    assert r.status_code == 200
    assert r.json()["results"][0]["summary"] == "found"


async def test_search_clamps_top_k_and_passes_filters(client):
    async with client as c:
        await c.post(
            "/context/search",
            json={"user_id": 1, "query": "x", "top_k": 999, "tags": ["person:mom"]},
        )
    call = app.state.db.search_context.await_args
    assert call.args[2] == 50  # top_k clamp ≤ 50
    assert call.kwargs["tags"] == ["person:mom"]


async def test_search_embed_failure_returns_502(client):
    app.state.embedder.embed = AsyncMock(side_effect=RuntimeError("boom"))
    async with client as c:
        r = await c.post("/context/search", json={"user_id": 1, "query": "x"})
    assert r.status_code == 502


# --- /context/recent ---

async def test_recent_clamps_limit_and_passes_kind(client):
    async with client as c:
        r = await c.post(
            "/context/recent", json={"user_id": 1, "limit": 9999, "kind": "daily"}
        )
    assert r.status_code == 200
    assert r.json()["events"][0]["summary"] == "recent"
    call = app.state.db.recent_context.await_args
    assert call.args[1] == 200  # limit clamp ≤ 200
    assert call.kwargs["kind"] == "daily"


# --- /context/purge ---

async def test_purge_returns_deleted_count(client):
    async with client as c:
        r = await c.post("/context/purge", json={"user_id": 1, "kind": "sms"})
    assert r.json()["deleted"] == 7
    app.state.db.purge_context.assert_awaited_once()


# --- /context/pending + /context/update (context_summarize support) ---

async def test_pending_returns_events_with_payload(client):
    async with client as c:
        r = await c.post("/context/pending", json={"user_id": 1, "limit": 10})
    assert r.status_code == 200
    ev = r.json()["events"][0]
    assert ev["id"] == 5 and ev["payload"]["raw"] == "сирий"


async def test_update_reembeds_and_normalizes_tags(client):
    async with client as c:
        r = await c.post(
            "/context/update",
            json={"id": 5, "user_id": 1, "summary": "дозведено", "kind": "worklog", "tags": []},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["embedded"] is True
    assert body["tags"][0] == "kind:worklog"  # нормалізовано + re-embed
    app.state.db.update_context_event.assert_awaited_once()


async def test_update_redacts_secrets_in_summary(client):
    """C1 backstop: context_summarize-generated summary must not land secrets cleartext.

    context_update drives on every raw passport via the summarize job; without this the
    /ingest redaction was bypassed on the update path (sibling of the /ingest backstop)."""
    secret = "sk-jarvis-ABCDEF0123456789ABCDEF0123456789"
    async with client as c:
        r = await c.post(
            "/context/update",
            json={
                "id": 5,
                "user_id": 1,
                "summary": f"підсумок: токен {secret} і картка 4111 1111 1111 1111",
            },
        )
    assert r.status_code == 200
    call = app.state.db.update_context_event.await_args
    assert secret not in call.kwargs["summary"]
    assert "[REDACTED:card]" in call.kwargs["summary"]
    # redact BEFORE embed: the vector is computed on the redacted text, not the raw secret
    emb_arg = app.state.embedder.embed.await_args.args[0]
    assert secret not in emb_arg and "[REDACTED:card]" in emb_arg


async def test_update_404_when_not_found(client):
    app.state.db.update_context_event = AsyncMock(return_value=False)
    async with client as c:
        r = await c.post(
            "/context/update", json={"id": 99, "user_id": 1, "summary": "x"}
        )
    assert r.status_code == 404


async def test_update_rejects_empty_summary(client):
    async with client as c:
        r = await c.post("/context/update", json={"id": 5, "user_id": 1, "summary": "  "})
    assert r.status_code == 400


async def test_ledger_returns_aggregates(client):
    async with client as c:
        r = await c.post("/context/ledger", json={"user_id": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["by_kind"]["note"] == 2
    app.state.db.context_ledger.assert_awaited_once()
