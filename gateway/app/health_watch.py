"""Proactive health alerts — host-agent / Ollama / Docker → Telegram."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from .auth import computer_owner_ids
from .services import ServicesClient
from .telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.health_watch")

_STATE_KEY = "jarvis:health:state"


async def _fetch_stack(svc: ServicesClient) -> dict[str, bool]:
    dash = await svc.dashboard()
    if dash.get("error"):
        return {"tools": False, "ollama": False, "hostagent": False, "docker": False}
    return {
        "tools": True,
        "ollama": bool(dash.get("ollama_up")),
        "hostagent": bool(dash.get("hostagent_up")),
        "docker": bool(dash.get("docker_up")),
    }


def _labels() -> dict[str, str]:
    return {
        "tools": "Tools",
        "ollama": "Ollama",
        "hostagent": "Host-agent",
        "docker": "Docker",
    }


async def _load_state(redis: aioredis.Redis) -> dict[str, bool]:
    raw = await redis.get(_STATE_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {k: bool(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def _save_state(redis: aioredis.Redis, state: dict[str, bool]) -> None:
    await redis.set(_STATE_KEY, json.dumps(state))


async def _notify(tg: TelegramClient, user_ids: set[int], text: str) -> None:
    for uid in user_ids:
        try:
            await tg.send_message(uid, text, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001
            logger.warning("health alert to %s failed: %s", uid, exc)


async def check_and_alert(
    redis: aioredis.Redis,
    tg: TelegramClient,
    svc: ServicesClient,
    *,
    alert_ids: set[int] | None = None,
) -> dict[str, bool]:
    """Порівнює поточний стан з попереднім; шле алерти при зміні."""
    current = await _fetch_stack(svc)
    prev = await _load_state(redis)
    recipients = alert_ids if alert_ids is not None else computer_owner_ids()
    labels = _labels()

    if prev:
        down = [labels[k] for k, ok in current.items() if not ok and prev.get(k)]
        up = [labels[k] for k, ok in current.items() if ok and not prev.get(k, True)]
        if down and recipients:
            await _notify(
                tg,
                recipients,
                "🔴 <b>JARVIS health</b>\n\nНедоступно: "
                + ", ".join(down)
                + "\n\nПеревір autostart / hostagent / Ollama.",
            )
        if up and recipients:
            await _notify(
                tg,
                recipients,
                "✅ <b>JARVIS health</b>\n\nЗнову online: " + ", ".join(up),
            )

    await _save_state(redis, current)
    return current


async def health_watch_loop(
    redis: aioredis.Redis,
    tg: TelegramClient,
    svc: ServicesClient,
    interval: float,
    *,
    alert_ids: set[int] | None = None,
) -> None:
    """Фоновий полер здоров'я стеку."""
    logger.info("Health watch started (interval=%ss)", interval)
    while True:
        try:
            await check_and_alert(redis, tg, svc, alert_ids=alert_ids)
        except asyncio.CancelledError:
            logger.info("Health watch stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("health watch tick failed: %s", exc)
        await asyncio.sleep(interval)
