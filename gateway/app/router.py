"""Роутинг апдейтів Telegram → оркестратор (n8n). Текст + голос (STT)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .auth import is_allowed
from .orchestrator import Orchestrator
from .ratelimit import RateLimiter
from .telegram import TelegramClient
from .tts_client import TtsClient
from .whisper import WhisperClient

logger = logging.getLogger("jarvis.router")


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


def _extract_audio_file_id(message: dict[str, Any]) -> str | None:
    """file_id з голосового / аудіо повідомлення (None — якщо це не аудіо)."""
    for key in ("voice", "audio"):
        obj = message.get(key)
        if isinstance(obj, dict) and obj.get("file_id"):
            return str(obj["file_id"])
    return None


async def _transcribe(file_id: str, tg: TelegramClient, stt: WhisperClient) -> str:
    """Завантажує файл із Telegram і проганяє через Whisper. '' при помилці."""
    try:
        file_path = await tg.get_file_path(file_id)
        if not file_path:
            return ""
        audio = await tg.download_file(file_path)
    except httpx.HTTPError as exc:
        logger.error("voice download failed: %s", exc)
        return ""
    name = file_path.rsplit("/", 1)[-1] or "voice.ogg"
    return await stt.transcribe(audio, filename=name)


async def handle_update(
    update: dict[str, Any],
    tg: TelegramClient,
    orch: Orchestrator,
    stt: WhisperClient,
    limiter: RateLimiter,
    tts: TtsClient | None = None,
) -> None:
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
        file_id = _extract_audio_file_id(message)
        if file_id is None:
            # Файли/фото/відео підключаємо у наступних фазах.
            await tg.send_message(chat_id, "Поки що розумію текст і голос. Інші файли — скоро.")
            return
        text = await _transcribe(file_id, tg, stt)
        source = "voice"
        if not text:
            await tg.send_message(
                chat_id, "Не зміг розпізнати голосове 🤷 Спробуй ще раз або напиши текстом."
            )
            return
        # Покажемо, що саме почули, перш ніж відповідати.
        await tg.send_message(chat_id, f"🎤 {text}")

    reply = await orch.process(
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "type": source,
            "mode": "auto",
        }
    )
    await tg.send_message(chat_id, reply)

    # Голосова відповідь: якщо ввімкнено і користувач писав голосом — додатково шлемо аудіо.
    # Текст уже надіслано вище, тож збій TTS не лишає користувача без відповіді.
    if tts is not None and source == "voice" and reply:
        audio = await tts.synthesize(reply)
        if audio:
            await tg.send_voice(chat_id, audio)
