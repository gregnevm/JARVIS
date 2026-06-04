"""Роутинг Telegram: команди/дашборд/admin + Tools /agent. Текст + усі аудіо (STT)."""
from __future__ import annotations

import logging
from typing import Any

import httpx
import redis.asyncio as aioredis

from .auth import is_allowed
from .bot import handle_callback, handle_command, is_command
from .media import AUDIO_SOURCES, AudioMedia, audio_echo_label, extract_audio_media
from .ratelimit import RateLimiter
from .services import ServicesClient
from .telegram import TelegramClient
from .tools_client import ToolsClient
from .tts_client import TtsClient
from .whisper import WhisperClient

logger = logging.getLogger("jarvis.router")


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


async def _transcribe_media(
    media: AudioMedia, tg: TelegramClient, stt: WhisperClient
) -> str:
    try:
        file_path = await tg.get_file_path(media.file_id)
        if not file_path:
            return ""
        audio = await tg.download_file(file_path)
    except httpx.HTTPError as exc:
        logger.error("audio download failed (%s): %s", media.source, exc)
        return ""
    name = file_path.rsplit("/", 1)[-1] if file_path else media.filename
    return await stt.transcribe(audio, filename=name or media.filename)


async def handle_update(
    update: dict[str, Any],
    tg: TelegramClient,
    tools: ToolsClient,
    svc: ServicesClient,
    stt: WhisperClient,
    limiter: RateLimiter,
    redis: aioredis.Redis,
    tts: TtsClient | None = None,
) -> None:
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        user_id = (callback.get("from") or {}).get("id")
        if not is_allowed(user_id):
            return
        await handle_callback(callback, tg, svc, redis)
        return

    message = _extract_message(update)
    if message is None:
        return

    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return

    if not is_allowed(user_id):
        logger.warning("Ignored update from non-whitelisted user_id=%s", user_id)
        return

    if not await limiter.allow(int(user_id)):
        await tg.send_message(chat_id, "Забагато запитів 🙂 Почекай хвилинку і спробуй знову.")
        return

    text = message.get("text")
    source = "text"

    if not text:
        media = extract_audio_media(message)
        if media is None:
            await tg.send_message(
                chat_id,
                "Поки що розумію *текст* і *аудіо* (голосові, музика, відео-нотатки, "
                "відео з звуком, аудіо-файли).",
                parse_mode="Markdown",
            )
            return
        text = await _transcribe_media(media, tg, stt)
        source = media.source
        if not text:
            await tg.send_message(
                chat_id,
                "Не зміг розпізнати аудіо 🤷 Спробуй ще раз або напиши текстом.",
            )
            return
        await tg.send_message(chat_id, f"{audio_echo_label(media)} {text}")

    if is_command(text):
        await handle_command(text, int(chat_id), int(user_id), tg, svc, redis)
        return

    # Показуємо "typing…" поки агент думає (інференс на CPU може тривати секунди).
    await tg.send_chat_action(int(chat_id), "typing")

    reply = await tools.process(
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "type": source,
            "mode": "auto",
        }
    )
    await tg.send_message(chat_id, reply)

    if tts is not None and source in AUDIO_SOURCES and reply:
        audio = await tts.synthesize(reply)
        if audio:
            await tg.send_voice(chat_id, audio)
