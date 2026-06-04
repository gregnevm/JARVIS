"""Dataset export from session JSONL."""
import json

import pytest

from app import dataset_export
from app.config import settings


def test_to_sharegpt():
    rows = [{"user": "hi", "assistant": "hello there, how are you?", "mode": "chat", "user_id": 1}]
    out = dataset_export.to_sharegpt(rows)
    assert out[0]["conversations"][0]["from"] == "human"
    assert "hello" in out[0]["conversations"][1]["value"]


def test_write_sharegpt(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    sess = tmp_path / "logs" / "sessions"
    sess.mkdir(parents=True)
    row = {
        "ts": 1,
        "user_id": 7,
        "mode": "agent",
        "user": "test",
        "assistant": "x" * 30,
    }
    (sess / "user_7.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    dest = tmp_path / "twin" / "export" / "sharegpt.jsonl"
    info = dataset_export.write_sharegpt_jsonl(dest, user_id=7)
    assert info["total"] == 1
    assert dest.is_file()


def test_load_skips_short(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    sess = tmp_path / "logs" / "sessions"
    sess.mkdir(parents=True)
    (sess / "user_1.jsonl").write_text(
        json.dumps({"user": "a", "assistant": "short", "mode": "chat"}) + "\n",
        encoding="utf-8",
    )
    assert len(dataset_export.load_rows(1)) == 0
