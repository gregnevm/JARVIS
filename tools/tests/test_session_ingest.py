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
    # AO-5.1a: input_hash завжди; model/trace без значень не роздувають запис
    assert row["input_hash"] == session_ingest.short_hash("hi")
    assert "model" not in row and "trace" not in row


def test_append_turn_trace_fields(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "twin_url", "")
    trace = [{"tool": "calc", "args_hash": "a" * 16, "result_hash": "b" * 16, "result_len": 1}]
    session_ingest.append_turn(
        42,
        user_text="скільки буде 2+2",
        assistant_text="4",
        mode="agent",
        iters=2,
        model="qwen2.5:14b",
        trace=trace,
    )
    p = tmp_path / "logs" / "sessions" / "user_42.jsonl"
    row = json.loads(p.read_text(encoding="utf-8").strip())
    assert row["model"] == "qwen2.5:14b"
    assert row["trace"] == trace
    assert row["input_hash"] == session_ingest.short_hash("скільки буде 2+2")
