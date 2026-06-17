"""TC-0 storage — /team/* routes (squads/relationships/graph/delegates) via FakeDB.

Той самий підхід, що test_context_routes: підміна app.state.db, ASGI без lifespan.
Граф-ендпоінт перевіряє реальну доменну збірку OrgGraph із наборів FakeDB.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.main import app


class FakeTeamDB:
    def __init__(self) -> None:
        self.health = AsyncMock(return_value=True)
        self.create_squad = AsyncMock(
            return_value={"id": "sq1", "org_id": "o", "name": "Backend", "parent_id": None, "kind": "team"}
        )
        self.add_squad_member = AsyncMock(return_value=True)
        self.upsert_relationship = AsyncMock(return_value=True)
        self.upsert_delegate = AsyncMock(
            return_value={"id": "d1", "org_id": "o", "principal_id": "A",
                          "persona": {"tone": "dry"}, "scopes": ["read:self"], "proactive": False}
        )
        self.get_delegate = AsyncMock(return_value=None)
        # graph data: A,B in backend; A reports_to M
        self.list_squads = AsyncMock(return_value=[
            {"id": "backend", "org_id": "o", "name": "Backend", "parent_id": None, "kind": "team"},
        ])
        self.list_squad_members = AsyncMock(return_value=[
            {"squad_id": "backend", "user_id": "A", "title": None, "seniority": None},
            {"squad_id": "backend", "user_id": "B", "title": None, "seniority": None},
        ])
        self.list_relationships = AsyncMock(return_value=[
            {"org_id": "o", "src_user_id": "A", "dst_user_id": "M", "kind": "reports_to",
             "weight": 1.0, "source": "declared"},
        ])


@pytest.fixture()
def client():
    app.state.db = FakeTeamDB()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_create_squad(client):
    async with client as c:
        r = await c.post("/team/squads", json={"org_id": "o", "name": "Backend"})
    assert r.status_code == 200
    assert r.json()["id"] == "sq1"


async def test_create_squad_rejects_bad_kind(client):
    async with client as c:
        r = await c.post("/team/squads", json={"org_id": "o", "name": "X", "kind": "bogus"})
    assert r.status_code == 400


async def test_create_squad_requires_name(client):
    async with client as c:
        r = await c.post("/team/squads", json={"org_id": "o", "name": "  "})
    assert r.status_code == 400


async def test_list_squads_attaches_members(client):
    async with client as c:
        r = await c.get("/team/squads?org_id=o")
    assert r.status_code == 200
    squads = r.json()["squads"]
    backend = next(s for s in squads if s["id"] == "backend")
    assert {m["user_id"] for m in backend["members"]} == {"A", "B"}


async def test_relationship_rejects_bad_kind(client):
    async with client as c:
        r = await c.post("/team/relationships", json={"org_id": "o", "src": "A", "dst": "M", "kind": "loves"})
    assert r.status_code == 400


async def test_relationship_ok(client):
    async with client as c:
        r = await c.post("/team/relationships",
                         json={"org_id": "o", "src": "A", "dst": "M", "kind": "reports_to"})
    assert r.status_code == 200 and r.json()["ok"] is True


async def test_graph_builds_from_db_sets(client):
    async with client as c:
        r = await c.get("/team/graph?org_id=o&user_id=A")
    assert r.status_code == 200
    body = r.json()
    assert body["squads"] == ["backend"]
    assert body["manager_chain"] == ["M"]


async def test_delegate_upsert_and_404(client):
    async with client as c:
        r = await c.put("/team/delegates", json={"org_id": "o", "principal_id": "A", "persona": {"tone": "dry"}})
        assert r.status_code == 200 and r.json()["principal_id"] == "A"
        r2 = await c.get("/team/delegates/ZZZ?org_id=o")
        assert r2.status_code == 404


def test_migration_chain_includes_004():
    from pathlib import Path
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    f = versions / "004_team_ecosystem.py"
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert 'down_revision = "003_context_passports"' in text
    assert "CREATE TABLE IF NOT EXISTS squads" in text
    assert "ADD COLUMN IF NOT EXISTS visibility" in text
