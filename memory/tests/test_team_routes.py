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
        self.list_groups = AsyncMock(return_value=[
            {"chat_id": -100, "org_id": "o", "squad_id": None, "title": "Team", "ingest": "ambient"},
        ])
        self.get_group = AsyncMock(return_value=None)
        self.upsert_group = AsyncMock(
            return_value={"chat_id": -100, "org_id": "o", "squad_id": None, "title": "Team", "ingest": "ambient"}
        )
        self.upsert_group_member = AsyncMock(return_value=True)
        self._proc = {
            "id": "p1", "org_id": "o", "owner_user_id": "A", "squad_id": None,
            "title": "Onboarding", "template": None, "status": "draft",
            "steps": [
                {"id": "s1", "title": "docs", "assignee_user_id": "A", "kind": "human_task",
                 "status": "pending", "due": None, "depends_on": []},
                {"id": "s2", "title": "approve", "assignee_user_id": "M", "kind": "approval",
                 "status": "pending", "due": None, "depends_on": ["s1"]},
            ],
        }
        self.create_process = AsyncMock(return_value=self._proc)
        self.list_processes = AsyncMock(return_value=[self._proc])
        self.get_process = AsyncMock(return_value=self._proc)
        self.update_process = AsyncMock(return_value=True)
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
        self.bump_relationship = AsyncMock(return_value=2.0)


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


async def test_group_consent_validates_ingest(client):
    async with client as c:
        bad = await c.post("/team/groups/consent", json={"org_id": "o", "chat_id": -100, "ingest": "spy"})
        assert bad.status_code == 400
        ok = await c.post("/team/groups/consent",
                          json={"org_id": "o", "chat_id": -100, "ingest": "ambient", "title": "Team"})
        assert ok.status_code == 200 and ok.json()["ingest"] == "ambient"


async def test_get_group_defaults_off_when_unregistered(client):
    async with client as c:
        r = await c.get("/team/groups/-999")
    assert r.status_code == 200 and r.json()["ingest"] == "off"


async def test_group_member_upsert(client):
    async with client as c:
        r = await c.post("/team/groups/members", json={"chat_id": -100, "telegram_id": 5, "user_id": "A"})
    assert r.status_code == 200 and r.json()["ok"] is True


async def test_process_create_reports_ready(client):
    async with client as c:
        r = await c.post("/team/processes", json={"org_id": "o", "owner_user_id": "A", "title": "Onboarding"})
    assert r.status_code == 200
    # лише s1 готовий (s2 залежить від s1)
    assert r.json()["ready"] == ["s1"]


async def test_process_advance_via_engine(client):
    async with client as c:
        r = await c.post("/team/processes/p1/advance", json={"org_id": "o", "step_id": "s1", "status": "done"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["ready"] == ["s2"]      # s1 done → s2 розблоковано
    app.state.db.update_process.assert_awaited_once()


async def test_process_advance_invalid_status(client):
    async with client as c:
        r = await c.post("/team/processes/p1/advance", json={"org_id": "o", "step_id": "s1", "status": "bogus"})
    assert r.status_code == 400


async def test_process_get_404(client):
    app.state.db.get_process = AsyncMock(return_value=None)
    async with client as c:
        r = await c.get("/team/processes/zzz?org_id=o")
    assert r.status_code == 404


async def test_observe_bumps_collaborates(client):
    async with client as c:
        r = await c.post("/team/observe", json={"org_id": "o", "author": "A", "subjects": ["B", "A", "C"]})
    assert r.status_code == 200
    bumped = r.json()["bumped"]
    # A↔B, A↔C (self A пропущено); 2 ребра
    assert {(b["src"], b["dst"]) for b in bumped} == {("A", "B"), ("A", "C")}
    assert app.state.db.bump_relationship.await_count == 2


def test_migration_chain_includes_005():
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "005_processes.py"
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert 'down_revision = "004_team_ecosystem"' in text
    assert "CREATE TABLE IF NOT EXISTS processes" in text


def test_migration_chain_includes_004():
    from pathlib import Path
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    f = versions / "004_team_ecosystem.py"
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert 'down_revision = "003_context_passports"' in text
    assert "CREATE TABLE IF NOT EXISTS squads" in text
    assert "ADD COLUMN IF NOT EXISTS visibility" in text
