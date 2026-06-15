"""Platform Hooks API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_hooks_status(platform_client):
    platform_client.app.state.tools.hooks_status = AsyncMock(
        return_value={"hooks": [], "enabled": True}
    )
    r = platform_client.get("/platform/api/hooks", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
