"""JsonlLog — append-only JSONL (DESIGN §6.1 SessionLogger).

Сирі сесії = джерело для майбутніх training-датасетів. Одна відповідальність:
дописати запис, порахувати, віддати хвіст із індексу. Нічого більше (SRP).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlLog:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> int:
        """Дописує один запис; повертає новий загальний розмір (last_idx)."""
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.count()

    def count(self) -> int:
        if not self._path.is_file():
            return 0
        with self._path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def read_from(self, start_idx: int = 0) -> list[dict[str, Any]]:
        """Записи з індексу start_idx (0-based, по непорожніх рядках)."""
        if not self._path.is_file():
            return []
        out: list[dict[str, Any]] = []
        idx = 0
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if idx >= start_idx:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                idx += 1
        return out
