"""Стрім відповіді агента в Telegram через editMessageText (UX «друкує», як ChatGPT).

Шле плейсхолдер, споживає NDJSON-стрім із Tools і поступово редагує повідомлення:
delta → дописуємо текст, status → показуємо мітку інструмента (поки тексту нема).
Редагування тротлимо (ліміт Telegram ~1 edit/с на чат). Якщо стрім нічого не дав
або обірвався — тихий фолбек на класичний /agent, тим самим повідомленням.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import redis.asyncio as aioredis

from . import artifacts as app_artifacts
from .outbound import build_reply_markup, parse_directives, send_directives
from .telegram import TELEGRAM_MAX_LEN, TelegramClient, split_message
from .tools_client import ToolsClient

logger = logging.getLogger("jarvis.gateway.streaming")

_PLACEHOLDER = "✍️ думаю…"
_CURSOR = " ▌"
_MIN_EDIT_INTERVAL = 1.1  # с між editMessageText (Telegram ~1/с на чат)


async def stream_reply(
    tg: TelegramClient,
    tools: ToolsClient,
    chat_id: int,
    payload: dict[str, Any],
    react_message_id: int | None = None,
    *,
    redis: aioredis.Redis | None = None,
) -> str:
    """Стрімить відповідь у Telegram. Повертає фінальний текст (для TTS/запису).

    '' → плейсхолдер навіть не пішов (Telegram недоступний); хай роутер вирішує.
    """
    mid = await tg.send_message_id(chat_id, _PLACEHOLDER)
    if mid is None:
        return ""

    acc = ""
    shown = _PLACEHOLDER
    last_edit = 0.0
    final_text = ""

    async def maybe_edit(body: str, force: bool = False) -> None:
        nonlocal shown, last_edit
        body = body.strip()
        if not body or body == shown:
            return
        if not force and time.monotonic() - last_edit < _MIN_EDIT_INTERVAL:
            return
        await tg.edit_message_text(chat_id, mid, body[:TELEGRAM_MAX_LEN])
        shown = body
        last_edit = time.monotonic()

    try:
        async for ev in tools.stream(payload):
            if ev.get("done"):
                final_text = str(ev.get("text") or acc).strip()
                break
            delta = ev.get("delta")
            if isinstance(delta, str) and delta:
                acc += delta
                await maybe_edit(acc + _CURSOR)
                continue
            status = ev.get("status")
            if isinstance(status, str) and status and not acc:
                await maybe_edit(status)
                continue
            confirm = ev.get("confirm")
            if isinstance(confirm, dict) and confirm.get("code"):
                from .bot.computer import send_computer_confirm

                await send_computer_confirm(chat_id, confirm, tg)
    except httpx.HTTPError as exc:
        logger.error("stream transport error: %s", exc)

    if not final_text:
        final_text = acc.strip()
    if not final_text:
        # Стрім нічого не дав → класичний /agent; плейсхолдер стане відповіддю.
        final_text = await tools.process(payload)

    user_id = int(payload.get("user_id") or chat_id)
    if redis is not None:
        final_text = await app_artifacts.apply_app_directives(redis, user_id, final_text)
    # Вирізаємо директиви: текст редагуємо у плейсхолдер, медіа/кнопки/реакції — окремо.
    clean, directives = parse_directives(final_text)
    markup = build_reply_markup(directives)
    # Фіналізація: прибираємо курсор; якщо текст > ліміту — решта окремими повідомленнями.
    chunks = split_message(clean or "…")
    await tg.edit_message_text(chat_id, mid, chunks[0], reply_markup=markup)
    for extra in chunks[1:]:
        await tg.send_message(chat_id, extra)
    await send_directives(tg, chat_id, directives, react_message_id)
    if user_id is not None:
        from .bot.computer import maybe_send_confirm_from_text

        await maybe_send_confirm_from_text(chat_id, clean or final_text, tg)
    return clean or final_text
