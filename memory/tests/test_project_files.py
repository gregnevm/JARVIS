"""read_project_files_content — токен-бюджет інжекту (P1.7 → CA-2.5)."""
from __future__ import annotations

import pytest

from app.db import DB


class _Con:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    async def fetch(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
        return self._rows


class _Acquire:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _Con:
        return _Con(self._rows)

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def acquire(self) -> _Acquire:
        return _Acquire(self._rows)


def _db(rows: list[dict[str, str]]) -> DB:
    db = DB.__new__(DB)  # без реального конекту
    db._pool = _Pool(rows)  # type: ignore[assignment]
    return db


async def test_per_file_token_truncation():
    db = _db([
        {"name": "a.txt", "content": "x" * 8000},  # 2000 ток → обрізати
        {"name": "b.txt", "content": "y" * 40},
    ])
    out = await db.read_project_files_content(
        1, max_total_tokens=5000, max_per_file_tokens=500
    )
    assert len(out) == 2
    assert out[0]["content"].endswith("…[truncated]")
    assert len(out[0]["content"]) <= 500 * 4 + len("…[truncated]")
    assert out[1]["content"] == "y" * 40


async def test_total_token_budget_stops_inclusion():
    db = _db([
        {"name": "a", "content": "x" * 4000},  # 1000 ток
        {"name": "b", "content": "y" * 4000},  # 1000 ток
        {"name": "c", "content": "z" * 4000},  # не влізе у 2000
    ])
    out = await db.read_project_files_content(
        1, max_total_tokens=2000, max_per_file_tokens=2000
    )
    assert [o["name"] for o in out] == ["a", "b"]
