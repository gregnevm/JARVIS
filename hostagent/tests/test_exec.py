"""host-agent: auth, /health, /powershell, admin gating."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

TOKEN = "test-token-secret"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "token", TOKEN)
    monkeypatch.setattr(settings, "allow_admin", False)
    return TestClient(app)


def test_health_no_auth(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_powershell_requires_token(client: TestClient) -> None:
    r = client.post("/powershell", json={"script": "Write-Output 1"})
    assert r.status_code == 403


def test_powershell_bad_token(client: TestClient) -> None:
    r = client.post(
        "/powershell",
        json={"script": "Write-Output 1"},
        headers={"X-Hostagent-Token": "wrong"},
    )
    assert r.status_code == 403


def test_powershell_admin_blocked(client: TestClient) -> None:
    r = client.post(
        "/powershell",
        json={"script": "Write-Output 1", "as_admin": True},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r.status_code == 403


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="PowerShell on Windows only")
def test_powershell_non_admin(client: TestClient) -> None:
    r = client.post(
        "/powershell",
        json={"script": "Write-Output 42"},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == 0
    assert "42" in data["stdout"]


def test_fs_list_requires_absolute_path(client: TestClient, tmp_path) -> None:
    r = client.get(
        "/fs/list",
        params={"path": "relative/path"},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r.status_code == 400


def test_fs_list_outside_roots_returns_403(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(settings, "fs_roots", str(allowed))
    r = client.get(
        "/fs/list",
        params={"path": str(outside)},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r.status_code == 403
    assert "HOSTAGENT_FS_ROOTS" in r.json()["detail"]


def test_fs_list_and_read(client: TestClient, tmp_path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.txt").write_text("hello", encoding="utf-8")
    r = client.get(
        "/fs/list",
        params={"path": str(d)},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r.status_code == 200
    names = [e["name"] for e in r.json()["entries"]]
    assert "a.txt" in names

    r2 = client.get(
        "/fs/read",
        params={"path": str(d / "a.txt")},
        headers={"X-Hostagent-Token": TOKEN},
    )
    assert r2.status_code == 200
    assert r2.json()["content"] == "hello"


def test_cli_runs_echo(client: TestClient) -> None:
    with patch("app.main._run_cli") as mock_cli:
        mock_cli.return_value = {"stdout": "ok", "stderr": "", "code": 0}
        r = client.post(
            "/cli",
            json={"exe": "echo", "args": ["hi"]},
            headers={"X-Hostagent-Token": TOKEN},
        )
    assert r.status_code == 200
    assert r.json()["stdout"] == "ok"
