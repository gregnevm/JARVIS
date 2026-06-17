"""Push-нотифікації через ntfy (UnifiedPush, self-host friendly — суверенно, S1).

Сервер публікує в ntfy-топік; APK підписаний на нього (UnifiedPush). Дефолт off.
Альтернатива FCM (Google) — свідомо ntfy за замовч (S1). Best-effort: не валить джоб.
"""
from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger("jarvis.tools.push")


async def publish(message: str, title: str = "JARVIS") -> bool:
    """POST у ntfy-топік. true — доставлено (2xx). Off/без топіка/помилка → false."""
    if not settings.push_enabled:
        return False
    topic = settings.ntfy_topic.strip()
    if not topic or not message.strip():
        return False
    url = f"{settings.ntfy_url.rstrip('/')}/{topic}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(
                url,
                content=message.encode("utf-8"),
                headers={"Title": title},  # ASCII-заголовок; текст — у тілі (UTF-8)
            )
            r.raise_for_status()
        return True
    except httpx.HTTPError as exc:  # noqa: BLE001 — push нефатальний
        logger.warning("push failed: %s", type(exc).__name__)
        return False
