"""host-agent: /fs/glob — read-only recursive glob (AM-1.4.2)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

TOKEN = "test-token-secret"
H = {"X-Hostagent-Token": TOKEN}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "token", TOKEN)
    monkeypatch.setattr(settings, "fs_roots", "")
    return TestClient(app)


def _tree(root: Path) -> None:
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")
    (root / "notes.txt").write_text("z", encoding="utf-8")
    sub = root / "pkg"
    sub.mkdir()
    (sub / "c.py").write_text("c", encoding="utf-8")
    skip = root / ".git"
    skip.mkdir()
    (skip / "config").write_text("ignore", encoding="utf-8")


def test_glob_py_recursive(client: TestClient, tmp_path: Path) -> None:
    _tree(tmp_path)
    # rglob рекурсивний: '*.py' ловить і pkg/c.py
    r = client.get("/fs/glob", params={"root": str(tmp_path), "pattern": "*.py"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matches"] == ["a.py", "b.py", "pkg/c.py"]
    assert body["truncated"] is False


def test_glob_default_pattern_lists_all(client: TestClient, tmp_path: Path) -> None:
    _tree(tmp_path)
    r = client.get("/fs/glob", params={"root": str(tmp_path)}, headers=H)  # pattern default '*'
    assert r.status_code == 200, r.text
    matches = r.json()["matches"]
    assert "a.py" in matches and "notes.txt" in matches and "pkg/c.py" in matches


def test_glob_skips_vcs_dirs(client: TestClient, tmp_path: Path) -> None:
    _tree(tmp_path)
    r = client.get("/fs/glob", params={"root": str(tmp_path), "pattern": "**/*"}, headers=H)
    matches = r.json()["matches"]
    assert not any(".git" in m for m in matches)  # .git пропущено
    assert "pkg/" in matches  # каталог — із кінцевим '/'


def test_glob_max_results_truncates(client: TestClient, tmp_path: Path) -> None:
    _tree(tmp_path)
    r = client.get(
        "/fs/glob",
        params={"root": str(tmp_path), "pattern": "**/*.py", "max_results": 1},
        headers=H,
    )
    body = r.json()
    assert len(body["matches"]) == 1 and body["truncated"] is True


def test_glob_requires_token(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/fs/glob", params={"root": str(tmp_path)}, headers={"X-Hostagent-Token": "x"})
    assert r.status_code == 403


def test_glob_not_a_dir_404(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    r = client.get("/fs/glob", params={"root": str(f)}, headers=H)
    assert r.status_code == 404


def test_glob_respects_fs_roots(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(settings, "fs_roots", str(allowed))
    r = client.get("/fs/glob", params={"root": str(tmp_path / "other")}, headers=H)
    assert r.status_code == 403
