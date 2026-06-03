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
