"""Recent `/v1` request log (AP-3.4): capped Redis list for the console API-Logs tab.

Кожен `/v1`-запит пише компактний запис (ts/method/path/status/ms/key_id) у capped
list `jarvis:apilog` (LPUSH+LTRIM до _MAX). Запис — best-effort (не валить запит).
Per-org розшарування — поверх через tenant-context (key_id → org)."""
from __future__ import annotations

import json
import time
from typing import Any, Protocol

_KEY = "jarvis:apilog"
_MAX = 200


class _Redis(Protocol):
    async def lpush(self, key: str, *values: str) -> Any: ...
    async def ltrim(self, key: str, start: int, end: int) -> Any: ...
    async def lrange(self, key: str, start: int, end: int) -> Any: ...


class RequestLogStore:
    def __init__(self, redis: _Redis) -> None:
        self._r = redis

    async def record(self, *, method: str, path: str, status: int, ms: int, key_id: str) -> None:
        entry = json.dumps(
            {
                "ts": int(time.time()),
                "method": method,
                "path": path,
                "status": int(status),
                "ms": int(ms),
                "key_id": key_id or "root",
            }
        )
        try:
            await self._r.lpush(_KEY, entry)
            await self._r.ltrim(_KEY, 0, _MAX - 1)
        except Exception:  # noqa: BLE001 — лог не має ламати запит
            return

    async def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, _MAX))
        try:
            raw = await self._r.lrange(_KEY, 0, limit - 1)
        except Exception:  # noqa: BLE001
            return []
        out: list[dict[str, Any]] = []
        for r in raw or []:
            try:
                out.append(json.loads(r))
            except (ValueError, TypeError):
                continue
        return out
