"""Session JSONL ingest."""
import json

import pytest

from app import session_ingest
from app.config import settings


def test_append_turn(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "twin_url", "")
    session_ingest.append_turn(42, user_text="hi", assistant_text="hello", mode="chat", iters=0)
    p = tmp_path / "logs" / "sessions" / "user_42.jsonl"
    assert p.is_file()
    row = json.loads(p.read_text(encoding="utf-8").strip())
    assert row["user"] == "hi"
    assert row["mode"] == "chat"
