"""host-agent: /fs/edit_batch — транзакційний multi-file apply + dry_run (CA-4.3/4.4)."""
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
    monkeypatch.setattr(settings, "max_bytes", 100_000)
    return TestClient(app)


def _edit(path: Path, old: str, new: str) -> dict:
    return {"path": str(path), "old_string": old, "new_string": new}


def test_batch_all_succeed(client: TestClient, tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={"edits": [_edit(a, "x = 1", "x = 10"), _edit(b, "y = 2", "y = 20")]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok" and data["count"] == 2
    assert a.read_text(encoding="utf-8") == "x = 10\n"
    assert b.read_text(encoding="utf-8") == "y = 20\n"


def test_batch_rolls_back_on_mid_failure(client: TestClient, tmp_path: Path) -> None:
    """2-га правка не знаходить old_string → 1-ша має відкотитись (нічого не змінено)."""
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={"edits": [_edit(a, "x = 1", "x = 10"), _edit(b, "NOT_THERE", "z")]},
    )
    assert r.status_code == 422, r.text
    assert "rolled back" in r.json()["detail"]
    # обидва файли — як були
    assert a.read_text(encoding="utf-8") == "x = 1\n"
    assert b.read_text(encoding="utf-8") == "y = 2\n"


def test_batch_dry_run_writes_nothing(client: TestClient, tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={"edits": [_edit(a, "x = 1", "x = 10")], "dry_run": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "dry_run" and data["count"] == 1
    assert "x = 10" in data["results"][0]["diff"]  # diff показано
    assert a.read_text(encoding="utf-8") == "x = 1\n"  # файл не змінено
    assert not (tmp_path / ".jarvis_backup").exists()  # бекапів немає


def test_batch_preserves_crlf_per_file(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "w.txt"
    f.write_bytes(b"a\r\nb\r\nc\r\n")
    r = client.post(
        "/fs/edit_batch", headers=H, json={"edits": [_edit(f, "b", "B")]}
    )
    assert r.status_code == 200, r.text
    assert f.read_bytes() == b"a\r\nB\r\nc\r\n"


def test_batch_empty_rejected(client: TestClient) -> None:
    r = client.post("/fs/edit_batch", headers=H, json={"edits": []})
    assert r.status_code == 400


def test_batch_too_many_files_rejected(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "edit_batch_max_files", 2)
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={"edits": [_edit(f, "x", "y")] * 3},
    )
    assert r.status_code == 400 and "too many" in r.json()["detail"]


def test_batch_rollback_restores_same_file_true_original(
    client: TestClient, tmp_path: Path
) -> None:
    """Дві правки одного файлу, 3-тя (інший) валить батч → файл = TRUE original."""
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("v = 0\n", encoding="utf-8")
    b.write_text("k = 1\n", encoding="utf-8")
    r = client.post(
        "/fs/edit_batch",
        headers=H,
        json={
            "edits": [
                _edit(a, "v = 0", "v = 1"),
                _edit(a, "v = 1", "v = 2"),
                _edit(b, "NOPE", "z"),
            ]
        },
    )
    assert r.status_code == 422, r.text
    assert a.read_text(encoding="utf-8") == "v = 0\n"  # true original, не v = 1
    assert b.read_text(encoding="utf-8") == "k = 1\n"


def test_single_fs_edit_still_works(client: TestClient, tmp_path: Path) -> None:
    """Рефактор fs_edit через _compute_edit не зламав одиночний шлях."""
    f = tmp_path / "s.py"
    f.write_text("hello\n", encoding="utf-8")
    r = client.post(
        "/fs/edit", headers=H, json={"path": str(f), "old_string": "hello", "new_string": "world"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["occurrences"] == 1
    assert f.read_text(encoding="utf-8") == "world\n"
