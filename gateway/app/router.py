"""Роутинг Telegram: команди/дашборд/admin + Tools /agent.

Приймаємо БУДЬ-ЯКИЙ контент: текст, аудіо (STT), фото/документи/відео/анімації/
стікери (качаємо на диск і даємо агенту шлях), а також локацію/контакт/опитування
тощо (описуємо текстом). І так само можемо ПОВЕРТАТИ будь-які медіа (див. outbound).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis

from .auth import is_allowed
from .bot import handle_callback, handle_command, is_command
from .config import settings
from .media import (
    AUDIO_SOURCES,
    AudioMedia,
    FileAttachment,
    album_prompt,
    attachment_label,
    audio_echo_label,
    describe_non_file,
    extract_audio_media,
    extract_file_attachment,
    message_context,
)
from .outbound import deliver
from .ratelimit import RateLimiter
from .services import ServicesClient
from .streaming import stream_reply
from .telegram import TelegramClient
from .tools_client import ToolsClient
from .tts_client import TtsClient
from .whisper import WhisperClient

logger = logging.getLogger("jarvis.router")

# Скільки символів текстового файлу вшити прямо в промпт (решту агент дочитає parse_file).
_INLINE_TEXT_LIMIT = 4000
_INLINE_TEXT_EXT = frozenset(
    {".txt", ".md", ".csv", ".json", ".log", ".py", ".ini", ".yaml", ".yml", ".xml", ".html"}
)
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


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


def _safe_name(name: str) -> str:
    name = _SAFE_NAME_RE.sub("_", name).strip("._") or "file.bin"
    return name[:80]


async def _save_attachment(att: FileAttachment, tg: TelegramClient) -> str | None:
    """Качає вкладення у settings.upload_dir (спільний том /data з Tools). Шлях або None."""
    try:
        file_path = await tg.get_file_path(att.file_id)
        if not file_path:
            return None
        content = await tg.download_file(file_path)
    except httpx.HTTPError as exc:
        logger.error("attachment download failed (%s): %s", att.kind, exc)
        return None
    suffix = Path(file_path).suffix or Path(att.filename).suffix
    name = f"{uuid.uuid4().hex[:8]}_{_safe_name(att.filename)}"
    if suffix and not name.endswith(suffix):
        name += suffix
    dest_dir = Path(settings.upload_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        dest.write_bytes(content)
    except OSError as exc:
        logger.error("attachment save failed: %s", exc)
        return None
    return str(dest)


def _inline_text(path: str) -> str:
    """Якщо файл текстовий — вшиваємо його вміст прямо в промпт (без зовнішніх деп)."""
    if Path(path).suffix.lower() not in _INLINE_TEXT_EXT:
        return ""
    try:
        data = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return data[:_INLINE_TEXT_LIMIT]


async def _ingest_attachment(
    att: FileAttachment, tg: TelegramClient
) -> tuple[str, str] | None:
    """Готує (текст_для_агента, source) з файлового вкладення або None при невдачі."""
    path = await _save_attachment(att, tg)
    if path is None:
        return None
    meta = f"тип={att.kind}, ім'я={att.filename}"
    if att.mime_type:
        meta += f", MIME={att.mime_type}"
    lines = [f"Користувач надіслав файл ({meta}). Збережено: {path}."]
    if att.caption:
        lines.append(f"Підпис користувача: {att.caption}")
    inline = _inline_text(path)
    if inline:
        lines.append(f"Вміст файлу:\n{inline}")
    elif att.kind in ("document", "video", "animation"):
        lines.append(
            "Щоб прочитати документ (txt/pdf/docx/csv/...), виклич інструмент "
            f"parse_file зі шляхом {path}."
        )
    elif att.kind in ("photo", "sticker"):
        lines.append(
            f"Це зображення. Щоб зрозуміти його — виклич describe_image зі шляхом {path} "
            f"(або ocr_image, якщо там переважно текст/скрін)."
        )
    return "\n".join(lines), att.kind


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
        await handle_callback(callback, tg, svc, redis, tools)
        return

    # Inline-режим: @bot <запит> у будь-якому чаті.
    inline = update.get("inline_query")
    if isinstance(inline, dict):
        await _handle_inline_query(inline, tg, tools)
        return

    # Реакція (emoji) користувача на повідомлення бота.
    reaction = update.get("message_reaction")
    if isinstance(reaction, dict):
        await _handle_reaction(reaction, tg, tools, limiter, redis)
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

    # Альбом (media_group): кілька файлів одним постом → буферимо й обробляємо разом.
    if message.get("media_group_id"):
        await _handle_album(message, int(chat_id), int(user_id), tg, tools, redis)
        return

    text = message.get("text")
    source = "text"

    if not text:
        text, source = await _ingest_any(message, chat_id, tg, stt)
        if text is None:
            return  # вже відповіли користувачу (помилка/порожньо)

    if is_command(text):
        await handle_command(text, int(chat_id), int(user_id), tg, svc, redis)
        return

    # Контекст (reply/forward) підкладаємо агенту, не показуючи користувачу.
    ctx = message_context(message)
    agent_text = f"{ctx}\n{text}" if ctx else text

    # Показуємо "typing…" поки агент думає (інференс на CPU може тривати секунди).
    await tg.send_chat_action(int(chat_id), "typing")

    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "text": agent_text,
        "type": source,
        "mode": "auto",
    }
    reply = await _run_agent(
        tg, tools, int(chat_id), payload, message.get("message_id"), redis, int(user_id)
    )

    if tts is not None and source in AUDIO_SOURCES and reply:
        audio = await tts.synthesize(reply)
        if audio:
            await tg.send_voice(chat_id, audio)


async def _run_agent(
    tg: TelegramClient,
    tools: ToolsClient,
    chat_id: int,
    payload: dict[str, Any],
    react_message_id: int | None = None,
    redis: aioredis.Redis | None = None,
    user_id: int | None = None,
) -> str:
    """Виконує запит до агента й доставляє відповідь (текст + медіа/кнопки/реакції/канвас)."""
    if settings.enable_streaming:
        reply = await stream_reply(tg, tools, chat_id, payload, react_message_id, redis=redis)
        if not reply:
            reply = await tools.process(payload)
            reply = await deliver(
                tg, chat_id, reply, react_message_id, redis=redis, user_id=user_id
            )
        return reply
    reply = await tools.process(payload)
    return await deliver(
        tg, chat_id, reply, react_message_id, redis=redis, user_id=user_id
    )


# --------------------------------------------------------------------------- #
# Inline-режим: @bot <запит> → одна відповідь-стаття.
# --------------------------------------------------------------------------- #
async def _handle_inline_query(
    inline: dict[str, Any], tg: TelegramClient, tools: ToolsClient
) -> None:
    user_id = (inline.get("from") or {}).get("id")
    if not is_allowed(user_id):
        return
    query = str(inline.get("query") or "").strip()
    iq_id = str(inline.get("id") or "")
    if not query or not iq_id:
        return
    answer = await tools.process({"user_id": int(user_id), "text": query})
    # Inline не показує медіа-директив — лишаємо чистий текст.
    from .outbound import parse_directives

    clean, _ = parse_directives(answer)
    clean = clean or answer
    results = [
        {
            "type": "article",
            "id": uuid.uuid4().hex[:16],
            "title": "Відповідь JARVIS",
            "description": clean[:120],
            "input_message_content": {"message_text": clean[:4096]},
        }
    ]
    await tg.answer_inline_query(iq_id, results, cache_time=0)


# --------------------------------------------------------------------------- #
# Реакції користувача на повідомлення бота.
# --------------------------------------------------------------------------- #
def _new_reaction_emoji(reaction: dict[str, Any]) -> str | None:
    """Перший доданий emoji (new_reaction \\ old_reaction). None, якщо реакцію зняли."""
    new = reaction.get("new_reaction") or []
    old_emojis = {
        r.get("emoji") for r in (reaction.get("old_reaction") or []) if isinstance(r, dict)
    }
    for r in new:
        if isinstance(r, dict) and r.get("type") == "emoji" and r.get("emoji") not in old_emojis:
            return str(r.get("emoji"))
    return None


async def _handle_reaction(
    reaction: dict[str, Any],
    tg: TelegramClient,
    tools: ToolsClient,
    limiter: RateLimiter,
    redis: aioredis.Redis | None = None,
) -> None:
    if not settings.enable_reaction_replies:
        return
    user_id = (reaction.get("user") or {}).get("id")
    chat_id = (reaction.get("chat") or {}).get("id")
    if user_id is None or chat_id is None or not is_allowed(user_id):
        return
    emoji = _new_reaction_emoji(reaction)
    if not emoji:
        return  # реакцію зняли або це не emoji — ігноруємо (без лупів)
    if not await limiter.allow(int(user_id)):
        return
    prompt = (
        f"Користувач поставив реакцію {emoji} на твоє попереднє повідомлення. "
        "Відповідай дуже коротко (1 рядок), доречно до цієї реакції."
    )
    answer = await tools.process({"user_id": int(user_id), "text": prompt})
    await deliver(tg, int(chat_id), answer, redis=redis, user_id=int(user_id))


# --------------------------------------------------------------------------- #
# Альбоми (media_group): дебаунс-буфер у Redis; лідер-таск збирає й обробляє разом.
# --------------------------------------------------------------------------- #
async def _handle_album(
    message: dict[str, Any],
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    redis: aioredis.Redis,
) -> None:
    gid = str(message.get("media_group_id"))
    att = extract_file_attachment(message)
    key = f"album:{gid}"
    if att is not None:
        path = await _save_attachment(att, tg)
        if path:
            rec = {"path": path, "kind": att.kind, "filename": att.filename}
            try:
                await redis.rpush(key, json.dumps(rec, ensure_ascii=False))
                await redis.expire(key, 60)
            except Exception as exc:  # noqa: BLE001 — Redis недоступний → не блокуємо
                logger.error("album buffer failed: %s", exc)
    # Підпис альбому (на одному з елементів) — перший виграє.
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        try:
            await redis.set(f"{key}:cap", caption.strip(), nx=True, ex=60)
        except Exception:  # noqa: BLE001
            pass

    # Лідер — перший таск групи: він чекає й обробляє весь альбом.
    try:
        is_leader = await redis.set(f"{key}:lead", "1", nx=True, ex=60)
    except Exception:  # noqa: BLE001
        is_leader = True  # без Redis вважаємо себе лідером (одиничне фото)
    if not is_leader:
        return

    await asyncio.sleep(settings.album_collect_seconds)
    try:
        raw = await redis.lrange(key, 0, -1)
        cap = await redis.get(f"{key}:cap")
        await redis.delete(key, f"{key}:cap", f"{key}:lead")
    except Exception as exc:  # noqa: BLE001
        logger.error("album flush failed: %s", exc)
        return
    items = [json.loads(r) for r in raw] if raw else []
    if not items:
        return
    await tg.send_message(chat_id, f"🖼 прийняв альбом: {len(items)} файлів")
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "text": album_prompt(items, cap),
        "type": "album",
        "mode": "auto",
    }
    await _run_agent(
        tg, tools, chat_id, payload, message.get("message_id"), redis, user_id
    )


async def _ingest_any(
    message: dict[str, Any], chat_id: Any, tg: TelegramClient, stt: WhisperClient
) -> tuple[str | None, str]:
    """Перетворює будь-який нетекстовий контент на (текст_для_агента, source).

    (None, ...) → користувачу вже надіслана відповідь (помилка/порожньо), роутер виходить.
    """
    # 1) Аудіо → STT (голосові, музика, відео з аудіо, аудіо-документи).
    media = extract_audio_media(message)
    if media is not None:
        transcript = await _transcribe_media(media, tg, stt)
        if not transcript:
            await tg.send_message(
                chat_id, "Не зміг розпізнати аудіо 🤷 Спробуй ще раз або напиши текстом."
            )
            return None, "text"
        await tg.send_message(chat_id, f"{audio_echo_label(media)} {transcript}")
        return transcript, media.source

    # 2) Файли: фото/документ/відео/анімація/стікер → качаємо + опис для агента.
    att = extract_file_attachment(message)
    if att is not None:
        await tg.send_chat_action(int(chat_id), "typing")
        ingested = await _ingest_attachment(att, tg)
        if ingested is None:
            await tg.send_message(
                chat_id, "Не вдалося завантажити файл 🤷 Спробуй ще раз."
            )
            return None, "text"
        prompt, source = ingested
        await tg.send_message(chat_id, f"{attachment_label(att)} прийняв: {att.filename}")
        return prompt, source

    # 3) Контент без файлів: локація/венью/контакт/опитування/кубик/гра/...
    described = describe_non_file(message)
    if described:
        return described, "event"

    # 4) Зовсім нічого не розпізнали.
    await tg.send_message(
        chat_id,
        "Не вдалося розпізнати вміст 🤷 Надішли текст, файл, фото, голос або локацію.",
    )
    return None, "text"
