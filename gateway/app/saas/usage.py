"""Per-key usage metering (AP-2.4): request counts per key per day у Redis.

Лічильники в hash `jarvis:usage:{key_id}:{YYYYMMDD}` (поле `requests` + `ep:<path>`).
Запис — best-effort (ніколи не валить запит). `key_id` = id ключа або `"root"`.
Per-org агрегація додасться зверху через tenant-context (kid → org)."""
from __future__ import annotations

import time
from typing import Any, Protocol

_KEY = "jarvis:usage:{kid}:{day}"
_MAX_DAYS = 92


class _Redis(Protocol):
    async def hincrby(self, key: str, field: str, amount: int) -> Any: ...
    async def hgetall(self, key: str) -> Any: ...


def _day(ts: float | None = None) -> str:
    return time.strftime("%Y%m%d", time.gmtime(ts if ts is not None else time.time()))


class UsageStore:
    def __init__(self, redis: _Redis) -> None:
        self._r = redis

    async def record(self, key_id: str, endpoint: str) -> None:
        """Best-effort інкремент — будь-яка помилка Redis ковтається."""
        k = _KEY.format(kid=key_id, day=_day())
        try:
            await self._r.hincrby(k, "requests", 1)
            await self._r.hincrby(k, f"ep:{endpoint}", 1)
        except Exception:  # noqa: BLE001 — метеринг не має ламати запит
            return

    async def summary(self, key_id: str, days: int = 7) -> dict[str, Any]:
        days = max(1, min(days, _MAX_DAYS))
        now = time.time()
        total = 0
        by_day: dict[str, int] = {}
        by_endpoint: dict[str, int] = {}
        for i in range(days):
            data = await self._r.hgetall(_KEY.format(kid=key_id, day=_day(now - i * 86400)))
            data = data or {}
            req = int(data.get("requests", 0) or 0)
            if req:
                by_day[_day(now - i * 86400)] = req
            total += req
            for field, val in data.items():
                if str(field).startswith("ep:"):
                    ep = str(field)[3:]
                    by_endpoint[ep] = by_endpoint.get(ep, 0) + int(val or 0)
        return {
            "object": "usage",
            "key_id": key_id,
            "days": days,
            "total_requests": total,
            "by_day": by_day,
            "by_endpoint": by_endpoint,
        }
