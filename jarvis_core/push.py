"""ntfy-публікація (UnifiedPush) — спільний хелпер gateway/tools (P7 SSOT).

Суверенний push (S1): self-host ntfy або ntfy.sh, дефолт off (PUSH_ENABLED=false).
Best-effort за визначенням: будь-яка помилка → False, ніколи не кидає — push
нефатальний для викликача (джоб, підписник шини).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jarvis.core.push")


def _header_safe(value: str) -> str:
    """HTTP-заголовки — latin-1: не-latin-1 символи замінюємо, щоб не впасти
    UnicodeEncodeError на кирилиці в title (текст повідомлення йде в тілі UTF-8)."""
    return value.encode("latin-1", "replace").decode("latin-1")


async def publish_ntfy(
    *,
    url: str,
    topic: str,
    message: str,
    title: str = "JARVIS",
    click: str | None = None,
    enabled: bool = True,
    timeout: float = 10.0,
) -> bool:
    """POST у ntfy-топік. True — доставлено (2xx); off/порожній топік/помилка → False.

    `click` — deep-link (ntfy-заголовок `Click`): тап по нотифікації відкриває URL
    (канал апруву для confirm-mesh, SY-5).
    """
    if not enabled:
        return False
    topic = topic.strip()
    if not topic or not message.strip():
        return False
    headers = {"Title": _header_safe(title)}
    if click:
        headers["Click"] = _header_safe(click)
    target = f"{url.rstrip('/')}/{topic}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(target, content=message.encode("utf-8"), headers=headers)
            r.raise_for_status()
        return True
    except httpx.HTTPError as exc:  # noqa: BLE001 — push нефатальний
        logger.warning("ntfy push failed: %s", type(exc).__name__)
        return False
