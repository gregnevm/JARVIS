"""D.4 retrain scheduler."""
import json

import pytest

from app.config import settings
from app.train_scheduler import mark_exported, retrain_status


def test_retrain_not_ready(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "train_retrain_min_curated", 200)
    st = retrain_status()
    assert st["retrain_ready"] is False
    assert st["curated_since_export"] == 0


def test_retrain_ready_after_delta(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "train_retrain_min_curated", 5)
    sess = tmp_path / "logs" / "sessions"
    sess.mkdir(parents=True)
    rows = []
    for i in range(6):
        rows.append(
            json.dumps(
                {
                    "user": f"question {i}",
                    "assistant": "x" * 30,
                    "mode": "chat",
                }
            )
        )
    (sess / "user_1.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    st = retrain_status()
    assert st["curated_turns"] == 6
    assert st["retrain_ready"] is True
    mark_exported()
    st2 = retrain_status()
    assert st2["retrain_ready"] is False
    assert st2["curated_since_export"] == 0
