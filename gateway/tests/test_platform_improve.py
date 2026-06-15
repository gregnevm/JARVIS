"""Platform Self-improve API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_improve_status(platform_client):
    platform_client.app.state.tools.improve_status = AsyncMock(
        return_value={"enabled": True, "last_scan": None}
    )
    r = platform_client.get("/platform/api/improve/status", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
