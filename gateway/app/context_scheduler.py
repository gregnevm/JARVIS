"""In-app scheduler context-jobs (опційна автоматизація, gateway веде loop).

Періодично б'є tools `/context/jobs/*`: `context_summarize` кожен тік, а
`context_daily`+`context_retention` — раз на добу від `CONTEXT_DAILY_HOUR` (UTC),
з guard'ом останнього прогону в Redis (org-префікс). Дефолт off (ADR-008: запуск
із нагляду) — альтернатива зовнішньому cron на `/api/v1/context/jobs/*`.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import redis.asyncio as aioredis

from jarvis_core.context import DEFAULT_ORG_ID, redis_key

from .config import settings

logger = logging.getLogger("jarvis.gateway.context_scheduler")

ToolsPoster = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def plan_context_run(now: datetime, last_daily: str | None, daily_hour: int) -> list[str]:
    """Які джоби запускати зараз: summarize завжди; daily+retention раз на добу від daily_hour."""
    jobs = ["context_summarize"]
    if now.hour >= daily_hour and last_daily != now.date().isoformat():
        jobs += ["context_daily", "context_retention"]
    return jobs


def _daily_key(user_id: int) -> str:
    return redis_key(DEFAULT_ORG_ID, "ctx", "daily", str(user_id))


async def run_due(
    redis: aioredis.Redis,
    post: ToolsPoster,
    user_ids: list[int],
    *,
    now: datetime,
    daily_hour: int,
) -> dict[str, int]:
    """Один тік: для кожного user планує й виконує джоби. Повертає лічильники запусків."""
    ran = {"summarize": 0, "daily": 0, "retention": 0}
    today = now.date().isoformat()
    for uid in user_ids:
        try:
            raw_last = await redis.get(_daily_key(uid))
        except Exception:  # noqa: BLE001 — guard нефатальний
            raw_last = None
        last = raw_last.decode() if isinstance(raw_last, (bytes, bytearray)) else raw_last
        did_daily = False
        for name in plan_context_run(now, last, daily_hour):
            try:
                await post(f"/context/jobs/{name}", {"user_id": uid})
            except Exception as exc:  # noqa: BLE001 — один user не валить решту
                logger.warning("context job %s for %s failed: %s", name, uid, type(exc).__name__)
                continue
            ran[name.replace("context_", "")] += 1
            did_daily = did_daily or name == "context_daily"
        if did_daily:
            try:
                await redis.set(_daily_key(uid), today)
            except Exception:  # noqa: BLE001
                pass
    return ran


async def _default_post(path: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=300.0) as cli:
        r = await cli.post(f"{settings.tools_url.rstrip('/')}{path}", params=params)
        r.raise_for_status()
        out = r.json()
    return out if isinstance(out, dict) else {}


async def context_scheduler_loop(
    redis: aioredis.Redis,
    *,
    post: ToolsPoster | None = None,
    interval: float | None = None,
    daily_hour: int | None = None,
) -> None:
    poster = post or _default_post
    every = interval if interval is not None else settings.context_scheduler_interval
    hour = daily_hour if daily_hour is not None else settings.context_daily_hour
    logger.info("Context scheduler started (interval=%ss daily_hour=%s UTC)", every, hour)
    while True:
        try:
            ids = settings.context_scheduler_ids
            if ids:
                await run_due(
                    redis, poster, sorted(ids), now=datetime.now(timezone.utc), daily_hour=hour
                )
        except asyncio.CancelledError:
            logger.info("Context scheduler stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("context scheduler tick failed: %s", exc)
        await asyncio.sleep(every)
