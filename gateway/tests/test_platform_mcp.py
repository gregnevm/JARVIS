"""Platform MCP API."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_mcp_servers(platform_client):
    platform_client.app.state.tools.list_mcp_servers = AsyncMock(
        return_value={"servers": [{"name": "demo", "status": "ok"}]}
    )
    r = platform_client.get("/platform/api/mcp/servers", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["servers"][0]["name"] == "demo"
