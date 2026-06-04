"""Активні нагадування: запис у Redis ZSET. Шле gateway-поллер (ROADMAP E4).

Спільний Redis із gateway — тут пишемо (інструмент агента set_reminder),
а доставляє прострочене gateway/app/reminders.py. ZSET `reminders`:
score = unix-час спрацювання, member = JSON {id, user_id, text}.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import cast

import redis.asyncio as aioredis

from .config import settings

REMINDERS_KEY = "reminders"
_MAX_DELAY_MIN = 365 * 24 * 60  # стеля: 1 рік
_MAX_LIST = 20

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def aclose() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def add_reminder(user_id: int, delay_minutes: int, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "Порожнє нагадування — про що нагадати?"
    if delay_minutes <= 0:
        return "Час нагадування має бути в майбутньому (хвилин > 0)."
    delay_minutes = min(delay_minutes, _MAX_DELAY_MIN)
    due = int(time.time()) + delay_minutes * 60
    member = json.dumps(
        {"id": uuid.uuid4().hex[:8], "user_id": int(user_id), "text": text[:1000]},
        ensure_ascii=False,
    )
    try:
        await _client().zadd(REMINDERS_KEY, {member: due})
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося поставити нагадування: {exc}"
    return f"Нагадаю {datetime.fromtimestamp(due).strftime('%Y-%m-%d %H:%M')} ✅"


async def list_reminders(user_id: int) -> str:
    try:
        raw = await _client().zrange(REMINDERS_KEY, 0, -1, withscores=True)
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося прочитати нагадування: {exc}"
    rows = cast("list[tuple[str, float]]", raw)
    out: list[str] = []
    now_ts = int(time.time())
    for member, score in rows:
        try:
            rec = json.loads(member)
        except (ValueError, TypeError):
            continue
        if int(rec.get("user_id", 0)) != int(user_id):
            continue
        if int(score) < now_ts:
            continue
        when = datetime.fromtimestamp(int(score)).strftime("%Y-%m-%d %H:%M")
        rid = rec.get("id", "?")
        out.append(f"• <code>{rid}</code> [{when}] {rec.get('text', '')}")
        if len(out) >= _MAX_LIST:
            break
    return "\n".join(out) if out else "Активних нагадувань немає."


async def cancel_reminder(user_id: int, reminder_id: str) -> str:
    rid = (reminder_id or "").strip().lower()
    if not rid:
        return "Вкажи id нагадування (з /reminders)."
    try:
        raw = await _client().zrange(REMINDERS_KEY, 0, -1, withscores=True)
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося: {exc}"
    rows = cast("list[tuple[str, float]]", raw)
    removed = 0
    for member, _score in rows:
        try:
            rec = json.loads(member)
        except (ValueError, TypeError):
            continue
        if int(rec.get("user_id", 0)) != int(user_id):
            continue
        if str(rec.get("id", "")).lower() != rid:
            continue
        await _client().zrem(REMINDERS_KEY, member)
        removed += 1
    if removed:
        return f"Скасовано нагадувань: {removed} ✅"
    return f"Нагадування з id '{rid}' не знайдено."


async def cancel_all_reminders(user_id: int) -> str:
    try:
        raw = await _client().zrange(REMINDERS_KEY, 0, -1)
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося: {exc}"
    removed = 0
    for member in cast("list[str]", raw):
        try:
            rec = json.loads(member)
        except (ValueError, TypeError):
            continue
        if int(rec.get("user_id", 0)) != int(user_id):
            continue
        await _client().zrem(REMINDERS_KEY, member)
        removed += 1
    return f"Скасовано всі нагадування ({removed}) ✅" if removed else "Немає активних нагадувань."
