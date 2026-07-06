"""Push-нотифікації через ntfy (UnifiedPush, self-host friendly — суверенно, S1).

Сервер публікує в ntfy-топік; APK підписаний на нього (UnifiedPush). Дефолт off.
Альтернатива FCM (Google) — свідомо ntfy за замовч (S1). Best-effort: не валить джоб.
Транспорт — спільний `jarvis_core.push.publish_ntfy` (P7 SSOT: gateway-шина SY-B1
і confirm-push SY-5 користуються тим самим кодом; click = deep-link).
"""
from __future__ import annotations

from jarvis_core.push import publish_ntfy

from .config import settings


async def publish(message: str, title: str = "JARVIS", click: str | None = None) -> bool:
    """POST у ntfy-топік. true — доставлено (2xx). Off/без топіка/помилка → false."""
    return await publish_ntfy(
        enabled=settings.push_enabled,
        url=settings.ntfy_url,
        topic=settings.ntfy_topic,
        message=message,
        title=title,
        click=click,
    )
