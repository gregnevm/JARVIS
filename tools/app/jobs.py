"""Scheduled remote jobs — cron-style macro execution."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from .config import settings

_JOBS_KEY = "jarvis:jobs"

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def schedule_job(user_id: int, run_at: int, macro: str, note: str = "") -> str:
    job_id = uuid.uuid4().hex[:10]
    payload = json.dumps(
        {
            "id": job_id,
            "user_id": int(user_id),
            "macro": macro.strip(),
            "note": note.strip()[:200],
        },
        ensure_ascii=False,
    )
    await _client().zadd(_JOBS_KEY, {payload: float(run_at)})
    return job_id


async def due_jobs(now: int | None = None) -> list[dict[str, Any]]:
    cutoff = int(time.time()) if now is None else now
    raw = await _client().zrangebyscore(_JOBS_KEY, "-inf", cutoff, start=0, num=20)
    out: list[dict[str, Any]] = []
    for member in raw:
        member_s = str(member)
        try:
            rec = json.loads(member_s)
            if isinstance(rec, dict):
                out.append(rec)
        except json.JSONDecodeError:
            continue
        await _client().zrem(_JOBS_KEY, member_s)
    return out


async def list_jobs(user_id: int) -> str:
    raw = await _client().zrange(_JOBS_KEY, 0, -1, withscores=True)
    lines: list[str] = []
    for item in raw:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        member, score = item
        member_s = str(member)
        try:
            rec = json.loads(member_s)
        except json.JSONDecodeError:
            continue
        if int(rec.get("user_id", 0)) != int(user_id):
            continue
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(score)))
        lines.append(f"• {ts} — macro `{rec.get('macro', '?')}` ({rec.get('note', '')})")
    return "\n".join(lines) if lines else "Немає запланованих jobs."
