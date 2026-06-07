"""Спільний Redis store: JSON-документи + per-user індекс (LPUSH/LTRIM)."""
from __future__ import annotations

import json
import time
from typing import Any

from .redis_util import get_redis


def now_ts() -> int:
    return int(time.time())


class RedisIndexedStore:
    """TTL-backed JSON docs keyed by id + per-user LPUSH index."""

    def __init__(
        self,
        *,
        key_prefix: str,
        index_prefix: str,
        ttl: int | None = 86400,
        history_max: int = 50,
    ) -> None:
        self.key_prefix = key_prefix
        self.index_prefix = index_prefix
        self.ttl = ttl
        self.history_max = history_max

    def _key(self, doc_id: str) -> str:
        return f"{self.key_prefix}{doc_id}"

    def _index_key(self, user_id: int) -> str:
        return f"{self.index_prefix}{int(user_id)}"

    async def save(self, rec: dict[str, Any]) -> None:
        rec["updated_at"] = now_ts()
        kwargs: dict[str, Any] = {}
        if self.ttl is not None:
            kwargs["ex"] = self.ttl
        await get_redis().set(
            self._key(str(rec["id"])),
            json.dumps(rec, ensure_ascii=False),
            **kwargs,
        )

    async def get(self, doc_id: str) -> dict[str, Any] | None:
        raw = await get_redis().get(self._key(doc_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    async def index_append(self, user_id: int, doc_id: str) -> None:
        r = get_redis()
        idx = self._index_key(user_id)
        await r.lpush(idx, doc_id)
        await r.ltrim(idx, 0, self.history_max - 1)

    async def list_for_user(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 50))
        ids = await get_redis().lrange(self._index_key(int(user_id)), 0, lim - 1)
        out: list[dict[str, Any]] = []
        for doc_id in ids:
            rec = await self.get(str(doc_id))
            if rec:
                out.append(rec)
        return out
