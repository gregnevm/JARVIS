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
from .outbound import build_reply_markup, format_agent_html, parse_directives, send_directives
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
    user_id: int | None = None,
    message_thread_id: int | None = None,
) -> str:
    """Стрімить відповідь у Telegram. Повертає фінальний текст (для TTS/запису).

    '' → плейсхолдер навіть не пішов (Telegram недоступний); хай роутер вирішує.
    """
    uid = int(user_id if user_id is not None else payload.get("user_id") or chat_id)
    thread_id = message_thread_id
    if thread_id is None and payload.get("message_thread_id") is not None:
        thread_id = int(payload["message_thread_id"])

    mid = await tg.send_message_id(chat_id, _PLACEHOLDER, message_thread_id=thread_id)
    if mid is None:
        return ""

    acc = ""
    shown = _PLACEHOLDER
    last_edit = 0.0
    final_text = ""

    async def maybe_edit(body: str, force: bool = False, *, html: bool = False) -> None:
        nonlocal shown, last_edit
        body = body.strip()
        if not body or body == shown:
            return
        if not force and time.monotonic() - last_edit < _MIN_EDIT_INTERVAL:
            return
        text = format_agent_html(body) if html else body[:TELEGRAM_MAX_LEN]
        pm = "HTML" if html else None
        await tg.edit_message_text(
            chat_id,
            mid,
            text,
            parse_mode=pm,
            message_thread_id=thread_id,
        )
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
        final_text = await tools.process(payload)

    if redis is not None:
        final_text = await app_artifacts.apply_app_directives(redis, uid, final_text)

    clean, directives = parse_directives(final_text)
    markup = build_reply_markup(directives)
    chunks = split_message(clean or "…")
    await maybe_edit(chunks[0], force=True, html=True)
    if markup:
        await tg.edit_message_text(
            chat_id,
            mid,
            format_agent_html(chunks[0]),
            parse_mode="HTML",
            reply_markup=markup,
            message_thread_id=thread_id,
        )
    for extra in chunks[1:]:
        await tg.send_message(
            chat_id,
            format_agent_html(extra),
            parse_mode="HTML",
            message_thread_id=thread_id,
        )
    await send_directives(
        tg, chat_id, directives, react_message_id, message_thread_id=thread_id
    )
    from .bot.computer import maybe_send_confirm_from_text

    await maybe_send_confirm_from_text(chat_id, clean or final_text, tg)
    return clean or final_text
