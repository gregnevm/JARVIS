"""Маршрути app.main (FastAPI route layer Memory-сервісу) — RAG/historia/projects.

259-рядковий `main.py` має ~17 ендпоінтів і два спільні хелпери
(`_embed_or_502`, `_require_project`), але memory/tests досі не містив
ЖОДНОГО тесту, що проходить крізь сам ASGI app: `test_db.py`/`test_rag.py`/
`test_sessions.py`/`test_project_files.py` тестують DB- і RAG-шари
напряму, оминаючи валідацію запитів, 404-guard'и, обрізання полів і
толерантну до часткових помилок логіку `/store` — усе це живе ЛИШЕ в
route-層 `main.py`.

Підхід: НЕ запускати `lifespan` (він створює реальний `DB`/Redis-конект) —
підмінюємо `app.state.db`/`app.state.embedder` напряму ПІСЛЯ імпорту `app`,
і ходимо через `httpx.ASGITransport` (не викликає lifespan-події, лише
ASGI http-scope) — швидше й без мережі/БД, аналог `httpx.MockTransport`
з `test_services.py`/`test_tools_client_http.py`, але для ASGI-застосунку
замість зовнішнього HTTP-клієнта."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.main import app


class _FakeCon:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    async def fetch(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
        return self._rows


class _FakeAcquire:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _FakeCon:
        return _FakeCon(self._rows)

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakePool:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._rows)


class FakeDB:
    """Сентинел DB — кожен метод окремий AsyncMock (легко перевизначити в тесті)."""

    def __init__(self, schema_meta_rows: list[dict[str, str]] | None = None) -> None:
        self.health = AsyncMock(return_value=True)
        self.get_or_create_session = AsyncMock(return_value=1)
        self.add_message = AsyncMock(return_value=10)
        self.add_embedding = AsyncMock(return_value=None)
        self.search = AsyncMock(return_value=[{"content": "found"}])
        self.recent_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
        self.list_sessions = AsyncMock(return_value=[{"id": 1, "title": "s1"}])
        self.create_project = AsyncMock(return_value={"id": 1, "name": "proj"})
        self.list_projects = AsyncMock(return_value=[{"id": 1, "name": "proj"}])
        self.get_project = AsyncMock(return_value={"id": 1, "name": "proj"})
        self.update_project = AsyncMock(return_value={"id": 1, "name": "renamed"})
        self.delete_project = AsyncMock(return_value=True)
        self.list_project_files = AsyncMock(return_value=[{"id": 1, "name": "a.txt"}])
        self.read_project_files_content = AsyncMock(return_value=[{"name": "a.txt", "content": "x"}])
        self.add_project_file = AsyncMock(return_value=5)
        self.delete_project_file = AsyncMock(return_value=True)
        self.add_project_file_embedding = AsyncMock(return_value=None)
        self.clear_project_file_embeddings = AsyncMock(return_value=3)
        self.all_project_file_contents = AsyncMock(return_value=["alpha beta", "gamma"])
        self._pool = _FakePool(schema_meta_rows or [])

    @property
    def pool(self) -> _FakePool:
        return self._pool


class FakeEmbedder:
    """`embed` — AsyncMock: тести підміняють `return_value`/`side_effect` за потреби."""

    def __init__(self) -> None:
        self.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def client():
    """Без lifespan (не лізе в реальну БД/Redis) — напряму підміняємо app.state."""
    app.state.db = FakeDB()
    app.state.embedder = FakeEmbedder()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# --- /health ---

async def test_health_ok(client):
    async with client as c:
        r = await c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert "schema_meta" not in body
    assert "schema_warn" not in body


async def test_health_degraded_when_db_unhealthy(client):
    app.state.db.health = AsyncMock(return_value=False)
    async with client as c:
        r = await c.get("/health")
    assert r.json()["status"] == "degraded"


async def test_health_includes_schema_warn_on_embed_dim_mismatch(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "embed_dim", 1024)
    app.state.db = FakeDB(schema_meta_rows=[{"key": "embed_dim", "value": "768"}])
    async with client as c:
        r = await c.get("/health")
    body = r.json()
    assert body["schema_meta"] == {"embed_dim": "768"}
    assert "mismatch" in body["schema_warn"]


# --- /embed (через _embed_or_502) ---

async def test_embed_success(client):
    async with client as c:
        r = await c.post("/embed", json={"text": "привіт"})
    assert r.status_code == 200
    body = r.json()
    assert body["dim"] == 3
    assert body["embedding"] == [0.1, 0.2, 0.3]


async def test_embed_failure_returns_502_with_detail(client):
    app.state.embedder.embed = AsyncMock(side_effect=RuntimeError("ollama down"))
    async with client as c:
        r = await c.post("/embed", json={"text": "x"})
    assert r.status_code == 502
    assert "embed failed" in r.json()["detail"]
    assert "ollama down" in r.json()["detail"]


# --- /store ---

async def test_store_creates_session_when_not_given(client):
    async with client as c:
        r = await c.post("/store", json={"user_id": 1, "content": "коротке повідомлення"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == 1
    assert body["chunks_stored"] == 1
    app.state.db.get_or_create_session.assert_awaited_once_with(1)


async def test_store_uses_given_session_id(client):
    async with client as c:
        r = await c.post(
            "/store", json={"user_id": 1, "content": "текст", "session_id": 99}
        )
    assert r.status_code == 200
    assert r.json()["session_id"] == 99
    app.state.db.get_or_create_session.assert_not_awaited()


async def test_store_continues_past_failed_chunk_embed(client):
    """Документований у _embed_or_502 контраст: /store НЕ фейлиться на одному
    поганому chunk'у (логує + continue), на відміну від /embed і /search."""
    long_text = "a" * 1000  # chunk_text(800, overlap=100) -> 2 чанки
    app.state.embedder.embed = AsyncMock(
        side_effect=[RuntimeError("chunk1 boom"), [0.4, 0.5, 0.6]]
    )
    async with client as c:
        r = await c.post("/store", json={"user_id": 1, "content": long_text})
    assert r.status_code == 200
    body = r.json()
    assert body["chunks_stored"] == 1  # перший чанк не пройшов, другий — так
    assert app.state.db.add_embedding.await_count == 1


# --- /search, /history, /sessions ---

async def test_search_returns_results(client):
    async with client as c:
        r = await c.post("/search", json={"user_id": 1, "query": "шукаю"})
    assert r.status_code == 200
    assert r.json() == {"results": [{"content": "found"}]}


async def test_search_embed_failure_returns_502(client):
    app.state.embedder.embed = AsyncMock(side_effect=RuntimeError("boom"))
    async with client as c:
        r = await c.post("/search", json={"user_id": 1, "query": "x"})
    assert r.status_code == 502


async def test_history_uses_default_limit_when_not_given(client):
    from app.config import settings

    async with client as c:
        r = await c.post("/history", json={"user_id": 1})
    assert r.status_code == 200
    app.state.db.recent_messages.assert_awaited_once_with(1, settings.short_term_limit)


async def test_history_respects_explicit_limit(client):
    async with client as c:
        await c.post("/history", json={"user_id": 1, "limit": 7})
    app.state.db.recent_messages.assert_awaited_once_with(1, 7)


async def test_sessions_clamps_limit_to_1_30_range(client):
    async with client as c:
        await c.get("/sessions", params={"user_id": 1, "limit": 999})
        app.state.db.list_sessions.assert_awaited_once_with(1, 30)

        app.state.db.list_sessions.reset_mock()
        await c.get("/sessions", params={"user_id": 1, "limit": 0})
        app.state.db.list_sessions.assert_awaited_once_with(1, 1)


# --- /projects CRUD ---

async def test_projects_create_rejects_empty_name(client):
    async with client as c:
        r = await c.post("/projects", json={"user_id": 1, "name": "   "})
    assert r.status_code == 400
    assert r.json()["detail"] == "name required"


async def test_projects_create_truncates_name_and_prompt(client):
    async with client as c:
        await c.post(
            "/projects",
            json={"user_id": 1, "name": "x" * 250, "system_prompt": "y" * 9000},
        )
    args = app.state.db.create_project.await_args
    assert args is not None
    _user_id, name, prompt = args.args
    assert len(name) == 200
    assert len(prompt) == 8000


async def test_projects_get_404_when_missing(client):
    app.state.db.get_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.get("/projects/1", params={"user_id": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"


async def test_projects_get_includes_files_and_optional_content(client):
    async with client as c:
        r = await c.get("/projects/1", params={"user_id": 1, "include_content": True})
    body = r.json()
    assert body["files"] == [{"id": 1, "name": "a.txt"}]
    assert body["files_content"] == [{"name": "a.txt", "content": "x"}]


async def test_projects_get_omits_content_by_default(client):
    async with client as c:
        r = await c.get("/projects/1", params={"user_id": 1})
    assert "files_content" not in r.json()


async def test_projects_update_404_when_missing(client):
    app.state.db.update_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.patch("/projects/1", json={"user_id": 1, "name": "new"})
    assert r.status_code == 404


async def test_projects_update_passes_none_for_unset_fields(client):
    async with client as c:
        await c.patch("/projects/1", json={"user_id": 1, "name": "  new name  "})
    _proj_id, _user_id, kwargs = (
        app.state.db.update_project.await_args.args
        + (app.state.db.update_project.await_args.kwargs,)
    )
    assert kwargs["name"] == "new name"
    assert kwargs["system_prompt"] is None
    assert kwargs["archived"] is None


async def test_projects_delete_404_when_not_ok(client):
    app.state.db.delete_project = AsyncMock(return_value=False)
    async with client as c:
        r = await c.delete("/projects/1", params={"user_id": 1})
    assert r.status_code == 404


async def test_projects_delete_ok(client):
    async with client as c:
        r = await c.delete("/projects/1", params={"user_id": 1})
    assert r.json() == {"ok": True}


# --- project files (через _require_project) ---

async def test_project_file_add_404_when_project_missing(client):
    app.state.db.get_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.post(
            "/projects/1/files", json={"user_id": 1, "name": "a.txt", "content": "x"}
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"
    app.state.db.add_project_file.assert_not_awaited()


async def test_project_file_add_rejects_empty_name(client):
    async with client as c:
        r = await c.post(
            "/projects/1/files", json={"user_id": 1, "name": "  ", "content": "x"}
        )
    assert r.status_code == 400
    assert r.json()["detail"] == "name required"


async def test_project_file_add_success(client):
    async with client as c:
        r = await c.post(
            "/projects/1/files", json={"user_id": 1, "name": "doc.txt", "content": "hello"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 5 and body["name"] == "doc.txt"
    assert "chunks_indexed" in body  # CA-2.4: scoped-RAG indexing


async def test_project_files_list_404_when_project_missing(client):
    app.state.db.get_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.get("/projects/1/files", params={"user_id": 1})
    assert r.status_code == 404


async def test_project_file_delete_404_when_project_missing(client):
    app.state.db.get_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.delete("/projects/1/files/5", params={"user_id": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"


async def test_project_file_delete_404_when_file_missing(client):
    app.state.db.delete_project_file = AsyncMock(return_value=False)
    async with client as c:
        r = await c.delete("/projects/1/files/5", params={"user_id": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "file not found"


async def test_project_file_delete_success(client):
    async with client as c:
        r = await c.delete("/projects/1/files/5", params={"user_id": 1})
    assert r.json() == {"ok": True}


# --- CA-2.4: scoped-RAG indexing of project files ---

async def test_project_file_add_indexes_when_enabled(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "index_project_files", True)
    async with client as c:
        r = await c.post(
            "/projects/1/files",
            json={"user_id": 7, "name": "a.py", "content": "def f(): return 1"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 5
    assert body["chunks_indexed"] >= 1
    app.state.db.add_project_file_embedding.assert_awaited()
    # embed-чанк іде з тим самим project_id/user_id
    call = app.state.db.add_project_file_embedding.await_args
    assert call.args[0] == 7  # user_id
    assert call.args[3] == 1  # project_id


async def test_project_file_add_skips_index_when_disabled(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "index_project_files", False)
    async with client as c:
        r = await c.post(
            "/projects/1/files",
            json={"user_id": 7, "name": "a.py", "content": "x"},
        )
    assert r.json()["chunks_indexed"] == 0
    app.state.db.add_project_file_embedding.assert_not_awaited()


async def test_project_reindex_clears_then_reembeds(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "index_project_files", True)
    async with client as c:
        r = await c.post("/projects/1/reindex", json={"user_id": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["removed"] == 3  # FakeDB.clear_project_file_embeddings
    assert body["files"] == 2  # FakeDB.all_project_file_contents → 2 files
    assert body["indexed"] >= 2
    app.state.db.clear_project_file_embeddings.assert_awaited_once_with(1)


async def test_project_reindex_404_for_foreign_project(client):
    app.state.db.get_project = AsyncMock(return_value=None)
    async with client as c:
        r = await c.post("/projects/1/reindex", json={"user_id": 99})
    assert r.status_code == 404
