"""CA-6.5 Platform Coding tab — plan / review / tree / fix proxy."""
from unittest.mock import AsyncMock

AUTH = ("admin", "secret")


def test_coding_plan(platform_client):
    platform_client.app.state.tools.code_plan = AsyncMock(
        return_value={"id": "p1", "summary": "do x", "steps": [{"file": "a.py", "action": "edit", "risk": "low"}]}
    )
    r = platform_client.post("/platform/api/coding/plan", json={"text": "refactor"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json()["steps"][0]["file"] == "a.py"


def test_coding_plan_requires_text(platform_client):
    platform_client.app.state.tools.code_plan = AsyncMock(return_value={})
    r = platform_client.post("/platform/api/coding/plan", json={"text": "  "}, auth=AUTH)
    assert r.status_code == 400


def test_coding_review(platform_client):
    platform_client.app.state.tools.code_review = AsyncMock(
        return_value={"verdict": "changes_requested", "summary": "bug", "findings": []}
    )
    r = platform_client.post(
        "/platform/api/coding/review", json={"diff": "--- a\n+++ b\n"}, auth=AUTH
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "changes_requested"


def test_coding_tree(platform_client):
    platform_client.app.state.tools.repo_tree = AsyncMock(return_value={"tree": "a/\n  b.py", "path": ""})
    r = platform_client.post("/platform/api/coding/tree", json={"path": ""}, auth=AUTH)
    assert r.status_code == 200
    assert "b.py" in r.json()["tree"]


def test_coding_fix_creates_job(platform_client):
    platform_client.app.state.tools.create_coding_job = AsyncMock(
        return_value={"id": "c1", "type": "coding_task", "status": "queued"}
    )
    r = platform_client.post(
        "/platform/api/coding/fix",
        json={"exe": "pytest", "args": ["-k", "x"], "path": "/repo"},
        auth=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["id"] == "c1"


def test_coding_fix_requires_exe(platform_client):
    platform_client.app.state.tools.create_coding_job = AsyncMock(return_value={})
    r = platform_client.post("/platform/api/coding/fix", json={"exe": ""}, auth=AUTH)
    assert r.status_code == 400


def test_coding_error_surfaces_502(platform_client):
    platform_client.app.state.tools.code_review = AsyncMock(return_value={"error": "tools unavailable"})
    r = platform_client.post("/platform/api/coding/review", json={"diff": "x"}, auth=AUTH)
    assert r.status_code == 502
