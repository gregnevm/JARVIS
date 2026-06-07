"""Phase 7.2 Self-improving loop."""
from __future__ import annotations

import json

import pytest

from app import self_improve


def test_turn_fingerprint_stable():
    row = {"ts": 1, "user_id": 5, "user": "hello"}
    assert self_improve.turn_fingerprint(row) == self_improve.turn_fingerprint(row)


def test_review_approve_moves_to_approved(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_improve.settings, "data_dir", str(tmp_path))
    item = {
        "id": "abc123",
        "fingerprint": "fp1",
        "status": "pending",
        "user": "u",
        "assistant": "a" * 25,
    }
    self_improve._append_jsonl(self_improve._pending_path(), item)
    out = self_improve.review_items(["abc123"], "approve", reviewer="admin")
    assert out["approved"] == 1
    assert self_improve.list_pending() == []
    approved = self_improve._read_jsonl(self_improve._approved_path())
    assert len(approved) == 1
    assert approved[0]["id"] == "abc123"


@pytest.mark.asyncio
async def test_scan_queues_judge_pass(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(self_improve.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(self_improve.settings, "self_improve_enabled", True)
    sessions = tmp_path / "logs" / "sessions"
    sessions.mkdir(parents=True)
    row = {
        "ts": 99,
        "user_id": 1,
        "mode": "chat",
        "user": "What is JARVIS?",
        "assistant": "JARVIS is your local AI assistant on this machine.",
    }
    (sessions / "user_1.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    async def fake_judge(u, a):
        return True, "pass"

    monkeypatch.setattr(self_improve, "judge_turn", fake_judge)
    out = await self_improve.scan_sessions(user_id=1, limit=10)
    assert out["queued"] == 1
    pending = self_improve.list_pending()
    assert len(pending) == 1
    assert pending[0]["judge_pass"] is True
