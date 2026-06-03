from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlLog:
    def append(self, record: dict[str, Any]) -> int:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.count()

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def count(self) -> int:
        if not self._path.is_file():
            return 0
        with self._path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
