"""Platform Skills API."""
from unittest.mock import AsyncMock

import pytest

AUTH = ("admin", "secret")


@pytest.fixture
def client(platform_client):
    platform_client.app.state.tools.list_skills = AsyncMock(return_value=[{"id": "demo", "name": "Demo"}])
    platform_client.app.state.tools.set_active_skill = AsyncMock(return_value={"skill_id": "demo"})
    yield platform_client


def test_skills_list(client):
    r = client.get("/platform/api/skills", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["skills"][0]["id"] == "demo"
