"""Slack connector (P6) — post message / list channels via bot token."""
from __future__ import annotations

from typing import Any

import httpx

from ..config import settings

_API = "https://slack.com/api"


def is_configured() -> bool:
    return bool((settings.slack_bot_token or "").strip())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.slack_bot_token.strip()}"}


async def post_message(text: str, channel: str = "") -> str:
    if not is_configured():
        return "Slack не налаштовано (SLACK_BOT_TOKEN у .env)."
    text = (text or "").strip()
    if not text:
        return "Порожнє повідомлення."
    ch = (channel or settings.slack_default_channel or "").strip()
    if not ch:
        return "Канал не вказано (SLACK_DEFAULT_CHANNEL або аргумент channel)."
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as cli:
            resp = await cli.post(
                f"{_API}/chat.postMessage",
                headers=_headers(),
                json={"channel": ch, "text": text[:4000]},
            )
            data = resp.json()
    except httpx.HTTPError as exc:
        return f"Slack помилка: {exc}"
    if not isinstance(data, dict) or not data.get("ok"):
        return f"Slack API: {data.get('error') if isinstance(data, dict) else data}"
    return f"Повідомлення надіслано в {ch} ✅"


async def list_channels(limit: int = 10) -> str:
    if not is_configured():
        return "Slack не налаштовано (SLACK_BOT_TOKEN у .env)."
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as cli:
            resp = await cli.get(
                f"{_API}/conversations.list",
                headers=_headers(),
                params={"limit": max(1, min(limit, 50)), "types": "public_channel,private_channel"},
            )
            data = resp.json()
    except httpx.HTTPError as exc:
        return f"Slack помилка: {exc}"
    if not isinstance(data, dict) or not data.get("ok"):
        return f"Slack API: {data.get('error') if isinstance(data, dict) else data}"
    raw_channels = data.get("channels")
    channels: list[Any] = raw_channels if isinstance(raw_channels, list) else []
    lines: list[str] = []
    for ch in channels[:limit]:
        if isinstance(ch, dict):
            lines.append(f"• #{ch.get('name')} (id={ch.get('id')})")
    return "\n".join(lines) if lines else "Каналів не знайдено."
