"""TC-0 — Platform «Команда» proxy (squads/relationships/graph)."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_squads_list(platform_client):
    platform_client.app.state.tools.team_squads = AsyncMock(
        return_value={"squads": [{"id": "s1", "name": "Backend", "kind": "team", "members": []}], "org_id": "o"}
    )
    r = platform_client.get("/platform/api/team/squads", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["squads"][0]["name"] == "Backend"


def test_squad_create(platform_client):
    platform_client.app.state.tools.team_create_squad = AsyncMock(return_value={"id": "s2", "name": "Sales"})
    r = platform_client.post("/platform/api/team/squads", json={"name": "Sales", "kind": "department"}, auth=AUTH)
    assert r.status_code == 200 and r.json()["id"] == "s2"
    # org_id інжектовано з контексту
    assert "org_id" in platform_client.app.state.tools.team_create_squad.await_args.args[0]


def test_relationship_upsert(platform_client):
    platform_client.app.state.tools.team_upsert_relationship = AsyncMock(return_value={"ok": True})
    r = platform_client.post(
        "/platform/api/team/relationships", json={"src": "A", "dst": "M", "kind": "reports_to"}, auth=AUTH
    )
    assert r.status_code == 200 and r.json()["ok"] is True


def test_graph_lookup(platform_client):
    platform_client.app.state.tools.team_graph = AsyncMock(
        return_value={"user_id": "A", "manager_chain": ["M"], "squads": ["backend"]}
    )
    r = platform_client.get("/platform/api/team/graph?user_id=A", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["manager_chain"] == ["M"]


def test_process_create_and_list(platform_client):
    platform_client.app.state.tools.team_create_process = AsyncMock(
        return_value={"id": "p1", "status": "draft", "ready": ["s1"]}
    )
    platform_client.app.state.tools.team_processes = AsyncMock(return_value={"processes": [{"id": "p1"}]})
    r = platform_client.post(
        "/platform/api/processes", json={"owner_user_id": "A", "title": "Onboarding"}, auth=AUTH
    )
    assert r.status_code == 200 and r.json()["id"] == "p1"
    assert "org_id" in platform_client.app.state.tools.team_create_process.await_args.args[0]
    r2 = platform_client.get("/platform/api/processes", auth=AUTH)
    assert r2.json()["processes"][0]["id"] == "p1"


def test_process_advance(platform_client):
    platform_client.app.state.tools.team_advance_process = AsyncMock(
        return_value={"id": "p1", "status": "running", "ready": ["s2"]}
    )
    r = platform_client.post(
        "/platform/api/processes/p1/advance", json={"step_id": "s1", "status": "done"}, auth=AUTH
    )
    assert r.status_code == 200 and r.json()["ready"] == ["s2"]
