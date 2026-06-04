"""ModelRegistry — єдиний авторитет про версії LoRA (DESIGN.md §7.4, принцип P7).

Чистий stdlib `sqlite3`, без зовнішніх залежностей — тестується будь-де, без GPU.
Семантика статусів: register → `candidate`; promote → `active` (попередній active
стає `archived`); rollback → відновити n-й найсвіжіший `archived` як `active`.
Це база для Blue-Green деплою LoRA (ADR-006) і Memento/Command rollback.
"""
from __future__ import annotations

import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lora_versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version      TEXT NOT NULL UNIQUE,
    path         TEXT NOT NULL,
    eval_score   REAL,
    status       TEXT NOT NULL DEFAULT 'candidate',
    dataset_size INTEGER,
    train_epochs INTEGER,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes        TEXT
);
CREATE TABLE IF NOT EXISTS system_prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version    TEXT NOT NULL UNIQUE,
    content    TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class ModelRegistry:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- LoRA версії ---
    def register_lora(
        self,
        version: str,
        path: str,
        eval_score: float | None = None,
        dataset_size: int | None = None,
        train_epochs: int | None = None,
        notes: str | None = None,
    ) -> int:
        """Реєструє нову версію як `candidate`. version унікальна (UNIQUE)."""
        cur = self._conn.execute(
            "INSERT INTO lora_versions "
            "(version, path, eval_score, status, dataset_size, train_epochs, notes) "
            "VALUES (?, ?, ?, 'candidate', ?, ?, ?)",
            (version, path, eval_score, dataset_size, train_epochs, notes),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def promote(self, version: str) -> None:
        """Робить version активною; попередній active → archived. KeyError якщо нема."""
        row = self._conn.execute(
            "SELECT id FROM lora_versions WHERE version = ?", (version,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown version: {version}")
        self._conn.execute("UPDATE lora_versions SET status='archived' WHERE status='active'")
        self._conn.execute("UPDATE lora_versions SET status='active' WHERE version = ?", (version,))
        self._conn.commit()

    def get_active(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM lora_versions WHERE status='active' LIMIT 1"
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def rollback(self, n: int = 1) -> dict[str, Any] | None:
        """Поточний active → archived; n-й найсвіжіший archived → active. None якщо бракує."""
        archived = self._conn.execute(
            "SELECT * FROM lora_versions WHERE status='archived' ORDER BY id DESC"
        ).fetchall()
        if len(archived) < n or n < 1:
            return None
        target_id = int(archived[n - 1]["id"])
        self._conn.execute("UPDATE lora_versions SET status='archived' WHERE status='active'")
        self._conn.execute("UPDATE lora_versions SET status='active' WHERE id = ?", (target_id,))
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM lora_versions WHERE id = ?", (target_id,)
        ).fetchone()
        return _row_to_dict(row)

    def list_versions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM lora_versions ORDER BY id DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_version(self, version: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM lora_versions WHERE version = ?", (version,)
        ).fetchone()
        return _row_to_dict(row) if row is not None else None
