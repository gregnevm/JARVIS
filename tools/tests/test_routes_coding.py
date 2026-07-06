"""CA-6.5 — /coding/repo_tree route (тонка обгортка навколо coding_tools.repo_tree)."""
from __future__ import annotations

import pytest
from app.routes import coding
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    router = APIRouter()
    coding.register(router)
    app.include_router(router)
    return TestClient(app)


def test_repo_tree_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_tree(path, *, max_depth=3, user_id=0):  # noqa: ANN001
        return f"tree(path={path!r},depth={max_depth},uid={user_id})"

    monkeypatch.setattr("app.tools.coding_tools.repo_tree", _fake_tree)
    r = client.post("/coding/repo_tree", json={"user_id": 5, "path": "/repo", "max_depth": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "/repo"
    assert "depth=2" in body["tree"] and "uid=5" in body["tree"]


def test_repo_tree_defaults(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_tree(path, *, max_depth=3, user_id=0):  # noqa: ANN001
        return "ok"

    monkeypatch.setattr("app.tools.coding_tools.repo_tree", _fake_tree)
    r = client.post("/coding/repo_tree", json={"user_id": 1})
    assert r.status_code == 200
    assert r.json()["tree"] == "ok"
