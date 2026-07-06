"""Паспортна шина в gateway (SY-B1) — синглтон InProcBus + дефолтні підписники.

Wiring (S3: I/O тут, домен у `jarvis_core.bus`): ingest-шлях (`client_api/context.py`)
емітить ПІСЛЯ store, підписники вішаються лінивo при першому зверненні. Все за
прапором `ENABLE_PASSPORT_BUS` (ADR-008: реактивність — свідомо; off = як сьогодні).

Перший підписник (SY-B1.3): push ntfy на `priority:high` — важлива подія
(нагадування, confirm-запит) долітає на телефон хвилинами, а не добовим cron-ом.
"""
from __future__ import annotations

import logging

from jarvis_core.bus import BusMeta, InProcBus
from jarvis_core.passport import Passport
from jarvis_core.push import publish_ntfy

from .config import settings

logger = logging.getLogger("jarvis.gateway.bus")

# name підписника = анти-петля: паспорти з source=bus_push він не отримає.
PUSH_SUBSCRIBER_NAME = "bus_push"
HIGH_PRIORITY_PATTERN = ["priority:high"]

_bus: InProcBus | None = None


async def _push_high_priority(passport: Passport, meta: BusMeta) -> None:
    """priority:high → ntfy (best-effort; вимкнений push просто поверне False)."""
    delivered = await publish_ntfy(
        enabled=settings.push_enabled,
        url=settings.ntfy_url,
        topic=settings.ntfy_topic,
        message=passport.summary,
        title=f"JARVIS · {passport.kind}",
    )
    if delivered:
        logger.info("bus→push: kind=%s user=%s", passport.kind, meta.user_id)


def get_passport_bus() -> InProcBus:
    """Лінивий синглтон шини з дефолтними підписниками (один на процес gateway)."""
    global _bus
    if _bus is None:
        _bus = InProcBus()
        _bus.subscribe(
            HIGH_PRIORITY_PATTERN, _push_high_priority, name=PUSH_SUBSCRIBER_NAME
        )
    return _bus


def reset_passport_bus() -> None:
    """Для тестів: скинути синглтон (нова шина = чисті підписки)."""
    global _bus
    _bus = None
