"""Platform Research API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_research_create(platform_client):
    platform_client.app.state.tools.create_research_job = AsyncMock(
        return_value={"id": "j1", "status": "queued", "type": "deep_research"}
    )
    r = platform_client.post(
        "/platform/api/research",
        json={"query": "JARVIS architecture", "max_hops": 2},
        auth=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["id"] == "j1"
