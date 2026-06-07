"""Platform Subagents API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_subagents_spawn(platform_client):
    platform_client.app.state.tools.spawn_subagent = AsyncMock(
        return_value={"id": "s1", "status": "queued"}
    )
    platform_client.app.state.tools.list_subagents = AsyncMock(
        return_value=[{"id": "s1", "status": "done"}]
    )
    r = platform_client.post("/platform/api/subagents", json={"task": "research"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "s1"
