"""host-agent: /fs/edit — search-replace + unified-diff + .jarvis_backup (CA-1.1/1.3)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import (
    _apply_search_replace,
    _apply_unified_diff,
    _parse_hunks,
    app,
)

TOKEN = "test-token-secret"
H = {"X-Hostagent-Token": TOKEN}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "token", TOKEN)
    monkeypatch.setattr(settings, "fs_roots", "")  # без скоупу в тестах
    monkeypatch.setattr(settings, "max_bytes", 100_000)
    return TestClient(app)


# --- pure helpers ------------------------------------------------------------

def test_search_replace_unique() -> None:
    out, n = _apply_search_replace("a b c", "b", "X", replace_all=False)
    assert out == "a X c" and n == 1


def test_search_replace_not_found() -> None:
    with pytest.raises(HTTPException) as exc:
        _apply_search_replace("abc", "zzz", "X", replace_all=False)
    assert exc.value.status_code == 422


def test_search_replace_non_unique_blocks() -> None:
    with pytest.raises(HTTPException) as exc:
        _apply_search_replace("x x x", "x", "y", replace_all=False)
    assert exc.value.status_code == 422
    assert "unique" in exc.value.detail


def test_search_replace_all() -> None:
    out, n = _apply_search_replace("x x x", "x", "y", replace_all=True)
    assert out == "y y y" and n == 3


def test_parse_and_apply_diff() -> None:
    content = "line1\nline2\nline3\n"
    diff = (
        "--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n line1\n-line2\n+line2_edited\n line3\n"
    )
    hunks = _parse_hunks(diff)
    assert len(hunks) == 1
    out = _apply_unified_diff(content, diff)
    assert "line2_edited" in out and "line2\n" not in out
    assert out.startswith("line1\n") and out.endswith("line3\n")


def test_apply_diff_context_not_found() -> None:
    diff = "@@ -1 +1 @@\n-nope\n+yep\n"
    with pytest.raises(HTTPException) as exc:
        _apply_unified_diff("real content", diff)
    assert exc.value.status_code == 422


# --- endpoint ----------------------------------------------------------------

def test_fs_edit_requires_token(client: TestClient) -> None:
    r = client.post("/fs/edit", json={"path": "/x", "old_string": "a", "new_string": "b"})
    assert r.status_code == 403


def test_fs_edit_search_replace_writes_and_backs_up(
    client: TestClient, tmp_path: Path
) -> None:
    f = tmp_path / "code.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit",
        headers=H,
        json={
            "path": str(f),
            "mode": "search_replace",
            "old_string": "return 1",
            "new_string": "return 2",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["occurrences"] == 1
    assert f.read_text(encoding="utf-8") == "def foo():\n    return 2\n"
    # backup збережено з оригіналом
    backup = Path(body["backup"])
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "def foo():\n    return 1\n"
    assert "return 2" in body["diff"]


def test_fs_edit_non_unique_returns_422(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "d.py"
    f.write_text("x\nx\n", encoding="utf-8")
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(f), "old_string": "x", "new_string": "y"},
    )
    assert r.status_code == 422
    # файл не змінено
    assert f.read_text(encoding="utf-8") == "x\nx\n"


def test_fs_edit_diff_mode(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "e.py"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    diff = "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(f), "mode": "diff", "diff": diff},
    )
    assert r.status_code == 200, r.text
    assert f.read_text(encoding="utf-8") == "a\nB\nc\n"


def test_fs_edit_no_change_422(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "n.py"
    f.write_text("same\n", encoding="utf-8")
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(f), "old_string": "same", "new_string": "same"},
    )
    assert r.status_code == 422


def test_fs_edit_preserves_crlf(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "w.txt"
    f.write_bytes(b"a\r\nb\r\nc\r\n")
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(f), "old_string": "b", "new_string": "B"},
    )
    assert r.status_code == 200, r.text
    assert f.read_bytes() == b"a\r\nB\r\nc\r\n"


def test_fs_edit_missing_file_404(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(tmp_path / "nope.py"), "old_string": "a", "new_string": "b"},
    )
    assert r.status_code == 404
