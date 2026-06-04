"""Поллер активних нагадувань: дістає прострочені з Redis ZSET і шле в Telegram.

Пише їх tools (інструмент set_reminder) у спільний Redis. chat_id == user_id
(приватний чат бота). ZSET `reminders`: score=unix-час, member=JSON {id,user_id,text}.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import cast

import redis.asyncio as aioredis

from .telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.reminders")

REMINDERS_KEY = "reminders"
POLL_INTERVAL = 20.0


async def deliver_due(
    redis: aioredis.Redis, tg: TelegramClient, now: int | None = None
) -> int:
    """Шле всі прострочені нагадування (score <= now), видаляє з ZSET. Повертає к-сть."""
    cutoff = int(time.time()) if now is None else now
    try:
        raw = await redis.zrangebyscore(REMINDERS_KEY, "-inf", cutoff)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reminders zrangebyscore failed: %s", exc)
        return 0
    sent = 0
    for member in cast("list[str]", raw):
        try:
            rec = json.loads(member)
        except (ValueError, TypeError):
            rec = {}
        user_id = int(rec.get("user_id", 0)) if isinstance(rec, dict) else 0
        text = str(rec.get("text", "")).strip() if isinstance(rec, dict) else ""
        if user_id and text:
            await tg.send_message(user_id, f"⏰ Нагадування: {text}")
            sent += 1
        await redis.zrem(REMINDERS_KEY, member)
    return sent


async def reminder_loop(
    redis: aioredis.Redis, tg: TelegramClient, interval: float = POLL_INTERVAL
) -> None:
    """Фоновий цикл: щоінтервал доставляє прострочене. Живе весь час роботи gateway."""
    logger.info("Reminder poller started (every %.0fs)", interval)
    while True:
        try:
            # Спершу спимо: перша перевірка через інтервал, не на старті — щоб
            # короткоживучі lifespan-тести не чіпали Redis, а старт був дешевий.
            await asyncio.sleep(interval)
            n = await deliver_due(redis, tg)
            if n:
                logger.info("delivered %d reminder(s)", n)
        except asyncio.CancelledError:
            logger.info("Reminder poller stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("reminder loop error: %s", exc)
