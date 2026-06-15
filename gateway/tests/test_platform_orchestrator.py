"""Platform Orchestrator API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_orchestrator_spawn(platform_client):
    platform_client.app.state.tools.spawn_orchestrator = AsyncMock(
        return_value={"id": "o1", "status": "queued"}
    )
    platform_client.app.state.tools.list_orchestrator_runs = AsyncMock(
        return_value=[{"id": "o1", "status": "done"}]
    )
    r = platform_client.post("/platform/api/orchestrator", json={"task": "plan deploy"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "o1"

    r2 = platform_client.get("/platform/api/orchestrator", auth=AUTH)
    assert r2.status_code == 200
    assert r2.json()["runs"][0]["id"] == "o1"
