"""Тести JsonlLog SSOT (jarvis_core.llm.jsonl_log). Без мережі/БД, чисті."""
from __future__ import annotations

from pathlib import Path

from jarvis_core.llm.jsonl_log import JsonlLog


def test_append_and_count(tmp_path: Path) -> None:
    log = JsonlLog(tmp_path / "l.jsonl")
    assert log.count() == 0
    assert log.append({"a": 1}) == 1
    assert log.append({"b": 2}) == 2
    assert log.count() == 2


def test_read_from(tmp_path: Path) -> None:
    log = JsonlLog(tmp_path / "l.jsonl")
    for i in range(5):
        log.append({"i": i})
    assert log.read_from(0) == [{"i": i} for i in range(5)]
    assert log.read_from(3) == [{"i": 3}, {"i": 4}]
    assert log.read_from(5) == []


def test_read_missing_file(tmp_path: Path) -> None:
    assert JsonlLog(tmp_path / "none.jsonl").read_from() == []
    assert JsonlLog(tmp_path / "none.jsonl").count() == 0


def test_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "blanks.jsonl"
    log = JsonlLog(p)
    log.append({"i": 0})
    with p.open("a", encoding="utf-8") as f:
        f.write("\n   \n")
    log.append({"i": 1})
    assert log.count() == 2
    assert log.read_from() == [{"i": 0}, {"i": 1}]


def test_skips_corrupt_json(tmp_path: Path) -> None:
    p = tmp_path / "corrupt.jsonl"
    log = JsonlLog(p)
    log.append({"ok": 1})
    with p.open("a", encoding="utf-8") as f:
        f.write("{not valid json}\n")
    log.append({"ok": 2})
    # count is line-based (3), read_from skips the unparseable line (2 records)
    assert log.count() == 3
    assert log.read_from() == [{"ok": 1}, {"ok": 2}]


def test_unicode_preserved(tmp_path: Path) -> None:
    log = JsonlLog(tmp_path / "u.jsonl")
    log.append({"text": "привіт світ"})
    raw = (tmp_path / "u.jsonl").read_text(encoding="utf-8")
    assert "привіт світ" in raw  # ensure_ascii=False kept cyrillic literal
    assert log.read_from()[0]["text"] == "привіт світ"


def test_parent_dir_created(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c.jsonl"
    log = JsonlLog(nested)
    assert nested.parent.is_dir()  # __init__ mkdir(parents=True)
    log.append({"x": 1})
    assert log.count() == 1
