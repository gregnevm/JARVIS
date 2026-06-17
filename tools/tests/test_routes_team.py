"""TC-2 — tools /team/* proxy (gateway→tools→memory). Memory-client замокано."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.routes import team


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    router = APIRouter()
    team.register(router)
    app.include_router(router)
    app.state.memory = AsyncMock()
    return TestClient(app)


def test_group_ingest_proxies_memory(client: TestClient) -> None:
    client.app.state.memory.team_get = AsyncMock(
        return_value={"ingest": "ambient", "org_id": "o", "squad_id": None}
    )
    r = client.get("/team/group/-100/ingest")
    assert r.status_code == 200
    assert r.json()["ingest"] == "ambient"
    client.app.state.memory.team_get.assert_awaited_with("/team/groups/-100")


def test_group_ingest_defaults_off(client: TestClient) -> None:
    client.app.state.memory.team_get = AsyncMock(return_value={})
    r = client.get("/team/group/-100/ingest")
    assert r.json()["ingest"] == "off"


def test_group_member_proxies(client: TestClient) -> None:
    client.app.state.memory.team_post = AsyncMock(return_value={"ok": True})
    r = client.post("/team/group/member", json={"chat_id": -100, "telegram_id": 5, "user_id": "A"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_group_collect_builds_group_passport(client: TestClient) -> None:
    captured: dict[str, Any] = {}

    async def _ingest(store: dict[str, Any]) -> dict[str, Any]:
        captured.update(store)
        return {"id": 1, "inserted": True}

    client.app.state.memory.context_ingest = _ingest
    r = client.post(
        "/team/group/collect",
        json={"chat_id": -100, "user_id": 7, "summary": "deploy at 5", "from_name": "bob"},
    )
    assert r.status_code == 200 and r.json()["inserted"] is True
    assert captured["visibility"] == "squad"
    assert captured["group_ref"] == -100
    assert captured["kind"] == "group_msg"
    assert captured["tags"][0] == "kind:group_msg"


def test_group_collect_skips_empty(client: TestClient) -> None:
    client.app.state.memory.context_ingest = AsyncMock()
    r = client.post("/team/group/collect", json={"chat_id": -100, "user_id": 7, "summary": "  "})
    assert r.json().get("skipped") == "empty"
    client.app.state.memory.context_ingest.assert_not_awaited()
