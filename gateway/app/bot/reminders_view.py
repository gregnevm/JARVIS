"""Читання активних нагадувань з Redis (спільний ZSET із tools)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import cast

import redis.asyncio as aioredis

from ..reminders import REMINDERS_KEY
from .dashboard import esc

_MAX_LIST = 20


async def list_user_reminders(redis: aioredis.Redis, user_id: int) -> str:
    try:
        raw = await redis.zrange(REMINDERS_KEY, 0, -1, withscores=True)
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося прочитати нагадування: {exc}"
    rows = cast("list[tuple[str, float]]", raw)
    out: list[str] = []
    for member, score in rows:
        try:
            rec = json.loads(member)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict) or int(rec.get("user_id", 0)) != int(user_id):
            continue
        when = datetime.fromtimestamp(int(score)).strftime("%Y-%m-%d %H:%M")
        rid = rec.get("id", "?")
        out.append(f"• <code>{esc(str(rid))}</code> [{when}] {rec.get('text', '')}")
        if len(out) >= _MAX_LIST:
            break
    return "\n".join(out) if out else "Активних нагадувань немає."


def format_reminders_message(body: str) -> str:
    return (
        "⏰ <b>Нагадування</b>\n"
        f"<pre>{esc(body)}</pre>\n"
        "<i>Щоб додати — напиши: «нагадай через 30 хв купити хліб»</i>"
    )
