"""Platform Planning API (P3)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

AUTH = ("admin", "secret")


@pytest.fixture
def client(platform_client):
    platform_client.app.state.tools.create_plan = AsyncMock(
        return_value={"id": "abc", "status": "pending", "summary": "test"}
    )
    platform_client.app.state.tools.list_plans = AsyncMock(return_value=[{"id": "abc", "status": "pending"}])
    platform_client.app.state.tools.get_plan = AsyncMock(return_value={"id": "abc", "status": "approved"})
    platform_client.app.state.tools.approve_plan = AsyncMock(return_value={"id": "abc", "status": "approved"})
    platform_client.app.state.tools.deny_plan = AsyncMock(return_value={"id": "abc", "status": "denied"})
    yield platform_client


def test_plans_create(client):
    r = client.post("/platform/api/plans", json={"text": "build feature"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "abc"


def test_plans_approve(client):
    r = client.post("/platform/api/plans/abc/approve", json={}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
