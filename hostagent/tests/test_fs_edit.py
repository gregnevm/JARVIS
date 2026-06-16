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


def test_diff_line_anchored_no_midline_splice() -> None:
    # Регресія: '-export = 80' НЕ має сплайснутись у середину 'reexport = 80'.
    diff = "@@ -1 +1 @@\n-export = 80\n+export = 9090\n"
    with pytest.raises(HTTPException) as exc:
        _apply_unified_diff("  reexport = 80\n", diff)
    assert exc.value.status_code == 422  # whole-line не знайдено → відмова, не корупція


def test_diff_substring_line_not_falsely_ambiguous() -> None:
    # Регресія: 'port = 80' як хвіст 'export = 80' не має давати 'not unique'.
    content = "port = 80\nexport = 80\n"
    out = _apply_unified_diff(content, "@@ -1 +1 @@\n-port = 80\n+port = 8080\n")
    assert out == "port = 8080\nexport = 80\n"


def test_diff_multi_hunk_repeated_context() -> None:
    # Регресія: hunk#1 створює дубль контексту для hunk#2 — @@-офсет розрулює.
    content = "alpha\nbeta\ngamma\n"
    diff = "@@ -1 +1 @@\n-alpha\n+beta\n@@ -2 +2 @@\n-beta\n+BETA\n"
    out = _apply_unified_diff(content, diff)
    assert out == "beta\nBETA\ngamma\n"


def test_diff_pure_insertion() -> None:
    # Чиста вставка (before порожній) якориться на @@-позицію.
    content = "a\nc\n"
    out = _apply_unified_diff(content, "@@ -1,0 +2,1 @@\n+b\n")
    assert out == "a\nb\nc\n"


def test_diff_repeated_line_disambiguated_by_offset() -> None:
    content = "x\nx\nx\n"
    # Редагуємо саме другий 'x' (@@ -2).
    out = _apply_unified_diff(content, "@@ -2 +2 @@\n-x\n+Y\n")
    assert out == "x\nY\nx\n"


def test_fs_edit_large_file_above_max_bytes(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # max_bytes малий (6 KB), edit_max_bytes великий → 10 KB файл редагується.
    monkeypatch.setattr(settings, "max_bytes", 6000)
    monkeypatch.setattr(settings, "edit_max_bytes", 2_000_000)
    f = tmp_path / "big.py"
    body = "# pad line\n" * 1000  # ~10 KB > max_bytes
    f.write_text(body + "TARGET = 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit",
        headers=H,
        json={"path": str(f), "old_string": "TARGET = 1", "new_string": "TARGET = 2"},
    )
    assert r.status_code == 200, r.text
    assert "TARGET = 2" in f.read_text(encoding="utf-8")


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


# --- /fs/edit_batch — транзакційна multi-file правка + dry-run (CA-4.3/4.4) ----

def test_fs_edit_batch_applies_all(client: TestClient, tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "edits": [
                {"path": str(a), "old_string": "x = 1", "new_string": "x = 10"},
                {"path": str(b), "old_string": "y = 2", "new_string": "y = 20"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["count"] == 2
    assert a.read_text(encoding="utf-8") == "x = 10\n"
    assert b.read_text(encoding="utf-8") == "y = 20\n"


def test_fs_edit_batch_dry_run_writes_nothing(client: TestClient, tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "dry_run": True,
            "edits": [{"path": str(a), "old_string": "x = 1", "new_string": "x = 99"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "dry_run" and body["count"] == 1
    assert "x = 99" in body["edits"][0]["diff"]
    assert a.read_text(encoding="utf-8") == "x = 1\n"  # без запису


def test_fs_edit_batch_rolls_back_on_invalid_edit(client: TestClient, tmp_path: Path) -> None:
    # Перша правка валідна, друга — old_string не знайдено → весь батч відхилено,
    # перший файл НЕ змінено (валідація всіх до першого запису).
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "edits": [
                {"path": str(a), "old_string": "x = 1", "new_string": "x = 10"},
                {"path": str(b), "old_string": "NOPE", "new_string": "z"},
            ]
        },
    )
    assert r.status_code == 422
    assert a.read_text(encoding="utf-8") == "x = 1\n"  # перший файл недоторканий
    assert b.read_text(encoding="utf-8") == "y = 2\n"


def test_fs_edit_batch_rejects_duplicate_path(client: TestClient, tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("x = 1\ny = 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "edits": [
                {"path": str(a), "old_string": "x = 1", "new_string": "x = 2"},
                {"path": str(a), "old_string": "y = 1", "new_string": "y = 2"},
            ]
        },
    )
    assert r.status_code == 422
    assert "duplicate" in r.json()["detail"]
    assert a.read_text(encoding="utf-8") == "x = 1\ny = 1\n"


def test_fs_edit_batch_empty_400(client: TestClient) -> None:
    r = client.post("/fs/edit_batch", headers=H, json={"edits": []})
    assert r.status_code == 400


def test_fs_edit_batch_too_many_400(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "edit_batch_max", 1)
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "edits": [
                {"path": str(a), "old_string": "x", "new_string": "X"},
                {"path": str(b), "old_string": "y", "new_string": "Y"},
            ]
        },
    )
    assert r.status_code == 400 and "too many" in r.json()["detail"]
