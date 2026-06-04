"""Доставка відповіді в Telegram з підтримкою будь-яких медіа та елементів UI.

Агент може повертати не лише текст, а й медіа/кнопки/реакції — через директиви:

    [[photo:<src>|<підпис>]]
    [[document:<src>|<підпис>]]   (синонім: file)
    [[video:<src>|<підпис>]]
    [[audio:<src>|<підпис>]]
    [[animation:<src>|<підпис>]]
    [[voice:<src>]]
    [[sticker:<src>]]
    [[location:<шир>,<довг>]]
    [[buttons:Текст1 | https://url1 ;; Текст2 | cb:agt:action_id]]   (URL або cb:agt:…)
    [[reaction:🔥]]                                              (емодзі-реакція на запит)

<src> — це http(s) URL, локальний шлях (напр. /data/uploads/...) або Telegram file_id.
Директиви вирізаються з тексту; спершу шлемо чистий текст, потім кожне медіа.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from html import escape as html_escape
from typing import Any

from . import artifacts as app_artifacts
from .telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.outbound")

_DIRECTIVE_RE = re.compile(r"\[\[\s*(\w+)\s*:\s*(.*?)\s*\]\]", re.DOTALL)

_KINDS = {
    "photo": "photo",
    "image": "photo",
    "document": "document",
    "file": "document",
    "video": "video",
    "audio": "audio",
    "animation": "animation",
    "gif": "animation",
    "voice": "voice",
    "sticker": "sticker",
    "location": "location",
    "buttons": "buttons",
    "button": "buttons",
    "reaction": "reaction",
    "react": "reaction",
}

# Kinds, де "|" — це не «src|caption», а власний синтаксис.
_NO_CAPTION = {"location", "buttons", "reaction"}


@dataclass(frozen=True)
class Directive:
    kind: str
    src: str
    caption: str | None = None


def parse_directives(text: str) -> tuple[str, list[Directive]]:
    """Розбирає директиви. Повертає (чистий_текст, список_директив)."""
    if not text or "[[" not in text:
        return (text or "").strip(), []

    directives: list[Directive] = []

    def _take(match: re.Match[str]) -> str:
        kind = _KINDS.get(match.group(1).lower())
        if kind is None:
            return match.group(0)  # не наша директива — лишаємо
        payload = match.group(2).strip()
        if not payload:
            return ""
        if "|" in payload and kind not in _NO_CAPTION:
            src, caption = payload.split("|", 1)
            src, caption = src.strip(), caption.strip() or None
        else:
            src, caption = payload, None
        if not src:
            return ""
        directives.append(Directive(kind=kind, src=src, caption=caption))
        return ""

    clean = _DIRECTIVE_RE.sub(_take, text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, directives


def build_reply_markup(directives: list[Directive]) -> dict[str, Any] | None:
    """Збирає inline-клавіатуру з URL або callback (cb:agt:…) кнопок."""
    rows: list[list[dict[str, str]]] = []
    for d in directives:
        if d.kind != "buttons":
            continue
        for part in d.src.split(";;"):
            if "|" not in part:
                continue
            label, target = (x.strip() for x in part.split("|", 1))
            if not label:
                continue
            if target.startswith(("http://", "https://")):
                rows.append([{"text": label[:64], "url": target}])
            elif target.startswith("cb:"):
                data = target[3:][:64]
                if data.startswith("agt:"):
                    rows.append([{"text": label[:64], "callback_data": data}])
    return {"inline_keyboard": rows} if rows else None


def format_agent_html(text: str) -> str:
    """Безпечний HTML для Telegram: escape + базові теги з markdown-подібного тексту."""
    if not text:
        return ""
    raw = text.strip()
    if "<b>" in raw or "<code>" in raw or "<pre>" in raw:
        return raw[:4096]
    out = html_escape(raw)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out[:4096]


async def _send_one(
    tg: TelegramClient,
    chat_id: int,
    d: Directive,
    react_message_id: int | None,
    *,
    message_thread_id: int | None = None,
) -> None:
    try:
        if d.kind == "photo":
            await tg.send_photo(chat_id, d.src, d.caption)
        elif d.kind == "document":
            await tg.send_document(chat_id, d.src, d.caption)
        elif d.kind == "video":
            await tg.send_video(chat_id, d.src, d.caption)
        elif d.kind == "audio":
            await tg.send_audio(chat_id, d.src, d.caption)
        elif d.kind == "animation":
            await tg.send_animation(chat_id, d.src, d.caption)
        elif d.kind == "sticker":
            await tg.send_sticker(chat_id, d.src)
        elif d.kind == "voice":
            if isinstance(d.src, str) and os.path.isfile(d.src):
                with open(d.src, "rb") as fh:
                    await tg.send_voice(chat_id, fh.read(), d.caption)
            elif isinstance(d.src, str) and d.src.startswith(("http://", "https://")):
                await tg.send_audio(chat_id, d.src, d.caption)
            elif isinstance(d.src, bytes):
                await tg.send_voice(chat_id, d.src, d.caption)
            else:
                await tg.send_audio(chat_id, d.src, d.caption)
        elif d.kind == "location":
            lat, lon = (p.strip() for p in d.src.split(",", 1))
            await tg.send_location(chat_id, float(lat), float(lon))
        elif d.kind == "reaction" and react_message_id is not None:
            await tg.set_message_reaction(chat_id, react_message_id, d.src.strip())
    except (ValueError, IndexError) as exc:
        logger.warning("bad directive %s: %s", d, exc)


async def send_directives(
    tg: TelegramClient,
    chat_id: int,
    directives: list[Directive],
    react_message_id: int | None = None,
    *,
    message_thread_id: int | None = None,
) -> None:
    photos: list[Directive] = []
    rest: list[Directive] = []
    for d in directives:
        if d.kind == "buttons":
            continue
        if d.kind == "photo":
            photos.append(d)
        else:
            rest.append(d)
    if len(photos) >= 2:
        await tg.send_media_group(
            chat_id,
            [(d.src, d.caption) for d in photos],
            message_thread_id=message_thread_id,
        )
        photos = []
    for d in photos + rest:
        await _send_one(tg, chat_id, d, react_message_id, message_thread_id=message_thread_id)


async def deliver(
    tg: TelegramClient,
    chat_id: int,
    reply: str,
    react_message_id: int | None = None,
    *,
    redis: Any | None = None,
    user_id: int | None = None,
    message_thread_id: int | None = None,
    parse_html: bool = True,
) -> str:
    """Шле відповідь агента: текст (+кнопки) + медіа/реакції. [[app:…]] → Канвас."""
    body = reply
    if redis is not None and user_id is not None:
        body = await app_artifacts.apply_app_directives(redis, user_id, body)
    clean, directives = parse_directives(body)
    markup = build_reply_markup(directives)
    pm = "HTML" if parse_html and clean else None
    body = format_agent_html(clean) if pm else clean
    if body:
        await tg.send_message(
            chat_id,
            body,
            parse_mode=pm,
            reply_markup=markup,
            message_thread_id=message_thread_id,
        )
    elif not directives:
        await tg.send_message(chat_id, reply or "…", message_thread_id=message_thread_id)
    await send_directives(
        tg, chat_id, directives, react_message_id, message_thread_id=message_thread_id
    )
    return clean
