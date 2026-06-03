"""JsonlLog — append-only JSONL."""
from pathlib import Path

from app.session_log import JsonlLog


def test_append_and_count(tmp_path: Path):
    log = JsonlLog(tmp_path / "l.jsonl")
    assert log.count() == 0
    assert log.append({"a": 1}) == 1
    assert log.append({"b": 2}) == 2
    assert log.count() == 2


def test_read_from(tmp_path: Path):
    log = JsonlLog(tmp_path / "l.jsonl")
    for i in range(5):
        log.append({"i": i})
    assert log.read_from(0) == [{"i": i} for i in range(5)]
    assert log.read_from(3) == [{"i": 3}, {"i": 4}]
    assert log.read_from(5) == []


def test_read_missing_file(tmp_path: Path):
    assert JsonlLog(tmp_path / "none.jsonl").read_from() == []
    assert JsonlLog(tmp_path / "none.jsonl").count() == 0


def test_unicode_preserved(tmp_path: Path):
    log = JsonlLog(tmp_path / "u.jsonl")
    log.append({"text": "привіт світ"})
    assert log.read_from()[0]["text"] == "привіт світ"
