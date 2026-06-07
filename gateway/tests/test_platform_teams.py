"""Platform Teams API."""
from unittest.mock import AsyncMock

import pytest

AUTH = ("admin", "secret")


@pytest.fixture
def client(platform_client):
    platform_client.app.state.tools.spawn_team = AsyncMock(return_value={"id": "t1", "status": "queued"})
    platform_client.app.state.tools.list_teams = AsyncMock(return_value=[{"id": "t1", "status": "done"}])
    yield platform_client


def test_teams_spawn(client):
    r = client.post("/platform/api/teams", json={"task": "research topic"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "t1"
