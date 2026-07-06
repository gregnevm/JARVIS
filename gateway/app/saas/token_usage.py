"""Token-usage агрегати зі стору kind:usage (SY-6) — один SSOT на трьох споживачів.

Читає агрегат-паспорти (продукує tools `UsageMeter` під `ENABLE_USAGE_METERING`)
і сумує payload. Споживачі: `/v1/usage` (tokens-блок, AP-трек), /platform
cost-дашборд, kaizen O3 ECO — усі рахують ті самі рядки `context_events`,
тож розбіжність цифр структурно неможлива (DoD SY-6, D1).

Це НЕ Redis-лічильник запитів (`saas/usage.py` — requests per key): токени і
запити — різні виміри; спільна відповідь `/v1/usage` склеює обидва.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis_core.service_client import ServiceError, call_dict

from ..config import settings

logger = logging.getLogger("jarvis.gateway.token_usage")

_RECENT_LIMIT = 200  # агрегат-паспорти рідкі (~1/хв макс) → 200 покриває тижні


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, days))


def _event_ts(ev: dict[str, Any]) -> datetime | None:
    for key in ("event_ts", "created_at"):
        raw = ev.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def summarize_usage_events(events: list[dict[str, Any]], *, days: int = 7) -> dict[str, Any]:
    """Чиста агрегація: паспорти kind:usage → calls/tokens/by_model/by_day."""
    cutoff = _cutoff(days)
    calls = tok_out = tok_in = 0
    by_model: dict[str, dict[str, int]] = {}
    by_day: dict[str, int] = {}
    counted = 0
    for ev in events:
        ts = _event_ts(ev)
        if ts is not None and ts < cutoff:
            continue
        payload = ev.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        counted += 1
        calls += int(payload.get("calls") or 0)
        tok_out += int(payload.get("tokens_out") or 0)
        tok_in += int(payload.get("tokens_in") or 0)
        models = payload.get("by_model")
        if isinstance(models, dict):
            for name, m in models.items():
                if not isinstance(m, dict):
                    continue
                slot = by_model.setdefault(
                    str(name), {"calls": 0, "tokens_out": 0, "tokens_in": 0}
                )
                slot["calls"] += int(m.get("calls") or 0)
                slot["tokens_out"] += int(m.get("tokens_out") or 0)
                slot["tokens_in"] += int(m.get("tokens_in") or 0)
        if ts is not None:
            day = ts.date().isoformat()
            by_day[day] = by_day.get(day, 0) + int(payload.get("tokens_out") or 0)
    return {
        "object": "token_usage",
        "days": days,
        "enabled": settings.enable_usage_metering,
        "passports": counted,
        "calls": calls,
        "tokens_out": tok_out,
        "tokens_in": tok_in,
        "by_model": by_model,
        "by_day_tokens_out": dict(sorted(by_day.items())),
    }


async def token_usage_summary(days: int = 7) -> dict[str, Any]:
    """Агрегат за вікно: тягне kind:usage з memory і сумує. Graceful при збої."""
    try:
        data = await call_dict(
            settings.memory_url, "POST", "/context/recent",
            json={
                "user_id": settings.usage_meter_user_id,
                "limit": _RECENT_LIMIT,
                "kind": "usage",
                "tags": ["kind:usage"],
            },
            timeout=10.0, service="memory",
        )
    except ServiceError as exc:
        logger.warning("token usage fetch failed: %s", type(exc).__name__)
        return {
            "object": "token_usage", "days": days,
            "enabled": settings.enable_usage_metering,
            "error": "memory_unreachable",
        }
    events = data.get("events") or []
    return summarize_usage_events(list(events), days=days)
