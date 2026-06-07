"""Platform Connectors API (P6)."""
from unittest.mock import AsyncMock

import pytest

AUTH = ("admin", "secret")


@pytest.fixture
def client(platform_client):
    platform_client.app.state.tools.list_connectors = AsyncMock(
        return_value={
            "notion": {"configured": False},
            "slack": {"configured": False},
            "calendar": {"configured": False},
        }
    )
    yield platform_client


def test_connectors_status(client):
    r = client.get("/platform/api/connectors", auth=AUTH)
    assert r.status_code == 200
    assert "notion" in r.json()
