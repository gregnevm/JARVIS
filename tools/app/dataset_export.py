"""Експорт session JSONL → ShareGPT / training JSONL (Фаза 3 A.3, C.2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings

_MIN_USER_LEN = 3
_MIN_ASSIST_LEN = 20
_SKIP_SUBSTR = (
    "Computer Use вимкнено",
    "Ліміт computer",
    "Невідомий інструмент",
    "[[COMPUTER_CONFIRM",
    "[[COMPUTER_ADMIN_CONFIRM",
)
_ALLOWED_MODES = frozenset({"agent", "hybrid", "computer", "chat"})


def _sessions_dir() -> Path:
    return Path(settings.data_dir) / "logs" / "sessions"


def iter_session_files(user_id: int | None = None) -> list[Path]:
    base = _sessions_dir()
    if not base.is_dir():
        return []
    if user_id is not None:
        p = base / f"user_{int(user_id)}.jsonl"
        return [p] if p.is_file() else []
    return sorted(base.glob("user_*.jsonl"))


def _row_ok(row: dict[str, Any], *, min_assist: int) -> bool:
    user = str(row.get("user", "")).strip()
    assist = str(row.get("assistant", "")).strip()
    if len(user) < _MIN_USER_LEN or len(assist) < min_assist:
        return False
    mode = str(row.get("mode", ""))
    if mode and mode not in _ALLOWED_MODES:
        return False
    for needle in _SKIP_SUBSTR:
        if needle in assist or needle in user:
            return False
    return True


def load_rows(
    user_id: int | None = None,
    *,
    limit: int = 0,
    min_assist: int = _MIN_ASSIST_LEN,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in iter_session_files(user_id):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not _row_ok(row, min_assist=min_assist):
                continue
            out.append(row)
            if limit > 0 and len(out) >= limit:
                return out
    return out


def to_sharegpt(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dataset: list[dict[str, Any]] = []
    for row in rows:
        dataset.append(
            {
                "conversations": [
                    {"from": "human", "value": str(row.get("user", ""))[:4000]},
                    {"from": "gpt", "value": str(row.get("assistant", ""))[:8000]},
                ],
                "metadata": {
                    "user_id": row.get("user_id"),
                    "mode": row.get("mode"),
                    "ts": row.get("ts"),
                },
            }
        )
    return dataset


def write_sharegpt_jsonl(
    dest: Path,
    *,
    user_id: int | None = None,
    limit: int = 0,
    train_ratio: float = 0.9,
) -> dict[str, Any]:
    rows = load_rows(user_id, limit=limit)
    dataset = to_sharegpt(rows)
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = len(dataset)
    split = int(n * train_ratio) if n else 0
    train_path = dest
    hold_path = dest.with_name(dest.stem + "_holdout" + dest.suffix)
    with train_path.open("w", encoding="utf-8") as f:
        for rec in dataset[:split]:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with hold_path.open("w", encoding="utf-8") as f:
        for rec in dataset[split:]:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "total": n,
        "train": split,
        "holdout": n - split,
        "train_path": str(train_path),
        "holdout_path": str(hold_path),
    }


def session_stats(user_id: int | None = None) -> dict[str, Any]:
    files = iter_session_files(user_id)
    raw_count = 0
    for path in files:
        try:
            raw_count += sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
        except OSError:
            pass
    all_rows = load_rows(user_id)
    by_mode: dict[str, int] = {}
    for row in all_rows:
        m = str(row.get("mode", "?"))
        by_mode[m] = by_mode.get(m, 0) + 1
    return {
        "files": len(files),
        "raw_turns": raw_count,
        "curated_turns": len(all_rows),
        "by_mode": by_mode,
    }
