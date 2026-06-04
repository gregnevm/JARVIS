"""Витяг аудіо з будь-якого Telegram-повідомлення для STT (Whisper)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Типи, після яких можна відповісти голосом (TTS), якщо увімкнено.
AUDIO_SOURCES = frozenset({"voice", "audio", "video_note", "video", "document"})

_AUDIO_EXT = frozenset(
    {
        ".ogg",
        ".oga",
        ".opus",
        ".mp3",
        ".m4a",
        ".wav",
        ".flac",
        ".aac",
        ".wma",
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
    }
)

_MIME_AUDIO = re.compile(r"^audio/", re.I)
_MIME_VIDEO = re.compile(r"^video/", re.I)


@dataclass(frozen=True)
class AudioMedia:
    file_id: str
    filename: str
    source: str
    mime_type: str | None = None
    title: str | None = None


def _guess_filename(source: str, file_name: str | None, mime: str | None) -> str:
    if file_name and "." in file_name:
        return file_name
    if mime:
        if "ogg" in mime or source == "voice":
            return "audio.ogg"
        if "mpeg" in mime or mime.endswith("/mp3"):
            return "audio.mp3"
        if "mp4" in mime or "video" in mime:
            return "audio.mp4"
        if "wav" in mime:
            return "audio.wav"
        if "webm" in mime:
            return "audio.webm"
    defaults = {
        "voice": "voice.ogg",
        "audio": "audio.mp3",
        "video_note": "video_note.mp4",
        "video": "video.mp4",
        "document": "document.bin",
    }
    return defaults.get(source, "audio.bin")


def _is_audio_document(mime: str, file_name: str) -> bool:
    if _MIME_AUDIO.match(mime):
        return True
    if _MIME_VIDEO.match(mime):
        return True
    lower = (file_name or "").lower()
    return any(lower.endswith(ext) for ext in _AUDIO_EXT)


def extract_audio_media(message: dict[str, Any]) -> AudioMedia | None:
    """Повертає аудіо-вкладення або None (не аудіо / не підтримується)."""
    for key in ("voice", "audio", "video_note", "video"):
        obj = message.get(key)
        if isinstance(obj, dict) and obj.get("file_id"):
            fid = str(obj["file_id"])
            mime = str(obj.get("mime_type") or "") or None
            fname = obj.get("file_name")
            if isinstance(fname, str):
                name = fname
            else:
                name = None
            title = obj.get("title") if key == "audio" else None
            return AudioMedia(
                file_id=fid,
                filename=_guess_filename(key, name, mime),
                source=key,
                mime_type=mime,
                title=str(title) if title else None,
            )

    doc = message.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        mime = str(doc.get("mime_type") or "")
        fname = str(doc.get("file_name") or "")
        if _is_audio_document(mime, fname):
            return AudioMedia(
                file_id=str(doc["file_id"]),
                filename=_guess_filename("document", fname or None, mime or None),
                source="document",
                mime_type=mime or None,
            )
    return None


def audio_echo_label(media: AudioMedia) -> str:
    """Підпис перед відповіддю агента (що розпізнали)."""
    icons = {
        "voice": "🎤",
        "audio": "🎵",
        "video_note": "📹",
        "video": "🎬",
        "document": "📎",
    }
    icon = icons.get(media.source, "🔊")
    title = f" — {media.title}" if media.title else ""
    return f"{icon}{title}"


# --------------------------------------------------------------------------- #
# Будь-який інший контент (фото/документ/відео/стікер/локація/контакт/...)
# Мета: ніколи не відмовляти. Файли — качаємо й даємо агенту шлях; решту —
# описуємо текстом, щоб модель могла зреагувати.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FileAttachment:
    """Завантажуване вкладення (має file_id), яке зберігаємо на диск для агента."""

    file_id: str
    kind: str  # photo | document | video | animation | sticker
    filename: str
    mime_type: str | None = None
    size: int | None = None
    caption: str | None = None


_KIND_ICON = {
    "photo": "🖼",
    "document": "📎",
    "video": "🎬",
    "animation": "🎞",
    "sticker": "🩷",
}

_KIND_DEFAULT_NAME = {
    "photo": "photo.jpg",
    "document": "document.bin",
    "video": "video.mp4",
    "animation": "animation.mp4",
    "sticker": "sticker.webp",
}


def _largest_photo(photos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Telegram шле фото кількома розмірами — беремо найбільший (останній/за площею)."""
    valid = [p for p in photos if isinstance(p, dict) and p.get("file_id")]
    if not valid:
        return None
    return max(valid, key=lambda p: int(p.get("width", 0)) * int(p.get("height", 0)))


def extract_file_attachment(message: dict[str, Any]) -> FileAttachment | None:
    """Будь-яке завантажуване вкладення, окрім аудіо (його ловить extract_audio_media).

    Повертає None, якщо у повідомленні немає файлів (фото/док/відео/анімація/стікер).
    """
    caption = message.get("caption")
    cap = caption if isinstance(caption, str) and caption.strip() else None

    photos = message.get("photo")
    if isinstance(photos, list):
        best = _largest_photo(photos)
        if best is not None:
            return FileAttachment(
                file_id=str(best["file_id"]),
                kind="photo",
                filename="photo.jpg",
                mime_type="image/jpeg",
                size=int(best["file_size"]) if isinstance(best.get("file_size"), int) else None,
                caption=cap,
            )

    for kind in ("animation", "video", "sticker", "document"):
        obj = message.get(kind)
        if not isinstance(obj, dict) or not obj.get("file_id"):
            continue
        mime = str(obj.get("mime_type") or "") or None
        fname = obj.get("file_name")
        name = fname if isinstance(fname, str) and fname else _KIND_DEFAULT_NAME[kind]
        size = obj.get("file_size")
        return FileAttachment(
            file_id=str(obj["file_id"]),
            kind=kind,
            filename=name,
            mime_type=mime,
            size=int(size) if isinstance(size, int) else None,
            caption=cap,
        )
    return None


def describe_non_file(message: dict[str, Any]) -> str | None:
    """Текстовий опис контенту без файлів: локація/венью/контакт/опитування/кубик/...

    Повертає рядок, який можна віддати агенту як вхід, або None, якщо такого немає.
    """
    loc = message.get("location")
    if isinstance(loc, dict) and "latitude" in loc and "longitude" in loc:
        lat, lon = loc["latitude"], loc["longitude"]
        return (
            f"📍 Локація: широта {lat}, довгота {lon} "
            f"(https://maps.google.com/?q={lat},{lon})."
        )

    venue = message.get("venue")
    if isinstance(venue, dict):
        title = venue.get("title", "")
        addr = venue.get("address", "")
        return f"📍 Місце: {title}, {addr}.".strip()

    contact = message.get("contact")
    if isinstance(contact, dict):
        parts = [
            contact.get("first_name", ""),
            contact.get("last_name", ""),
        ]
        name = " ".join(p for p in parts if p).strip()
        phone = contact.get("phone_number", "")
        return f"👤 Контакт: {name} {phone}".strip()

    poll = message.get("poll")
    if isinstance(poll, dict):
        q = poll.get("question", "")
        opts = [o.get("text", "") for o in poll.get("options", []) if isinstance(o, dict)]
        opts_txt = "; ".join(o for o in opts if o)
        return f"📊 Опитування: «{q}». Варіанти: {opts_txt}."

    dice = message.get("dice")
    if isinstance(dice, dict):
        return f"🎲 Кубик/слот {dice.get('emoji', '🎲')} випало {dice.get('value', '?')}."

    if isinstance(message.get("game"), dict):
        return f"🎮 Гра: {message['game'].get('title', '')}."

    if isinstance(message.get("story"), dict):
        return "📖 Користувач поділився історією (story)."

    return None


def attachment_label(att: FileAttachment) -> str:
    """Іконка-ехо для відповіді (що отримали)."""
    return _KIND_ICON.get(att.kind, "📁")


# --------------------------------------------------------------------------- #
# Контекст повідомлення: відповідь на повідомлення (reply) + переслане (forward).
# Підкладаємо агенту, щоб він розумів, на що саме реагує користувач.
# --------------------------------------------------------------------------- #
def _msg_snippet(msg: dict[str, Any], limit: int = 500) -> str:
    txt = msg.get("text") or msg.get("caption") or ""
    if not txt and isinstance(msg.get("poll"), dict):
        txt = f"[опитування] {msg['poll'].get('question', '')}"
    txt = str(txt).strip().replace("\n", " ")
    return txt[:limit]


def _forward_origin(message: dict[str, Any]) -> str | None:
    """Хто першоджерело пересланого повідомлення (нове й старе API Telegram)."""
    origin = message.get("forward_origin")
    if isinstance(origin, dict):
        otype = origin.get("type")
        if otype == "user":
            return (origin.get("sender_user") or {}).get("first_name") or "користувач"
        if otype == "hidden_user":
            return origin.get("sender_user_name") or "прихований користувач"
        if otype in ("channel", "chat"):
            chat = origin.get("chat") or origin.get("sender_chat") or {}
            return chat.get("title") or origin.get("author_signature") or "канал"
    fwd_user = message.get("forward_from")
    if isinstance(fwd_user, dict):
        return fwd_user.get("first_name") or "користувач"
    fwd_chat = message.get("forward_from_chat")
    if isinstance(fwd_chat, dict):
        return fwd_chat.get("title") or "канал"
    return None


def message_context(message: dict[str, Any]) -> str:
    """Текстовий префікс-контекст (reply/forward) або '' — для промпту агента."""
    lines: list[str] = []
    origin = _forward_origin(message)
    if origin:
        lines.append(f"[Переслано від: {origin}]")
    reply = message.get("reply_to_message")
    if isinstance(reply, dict):
        snip = _msg_snippet(reply)
        if snip:
            lines.append(f"[У відповідь на: «{snip}»]")
    return "\n".join(lines)


def album_prompt(items: list[dict[str, Any]], caption: str | None) -> str:
    """Зводить альбом (media_group) у єдиний запит для агента."""
    lines = [f"Користувач надіслав альбом із {len(items)} файлів:"]
    for it in items:
        meta = f"{it.get('kind', 'file')}: {it.get('path', '')}"
        lines.append(f"- {meta}")
    if caption:
        lines.append(f"Підпис: {caption}")
    lines.append(
        "Файли збережено на диску. Текстові/PDF/DOCX читай через parse_file, "
        "зображення — через describe_image/ocr_image (якщо доступні)."
    )
    return "\n".join(lines)
