"""Синтез мовлення: piper CLI (WAV) → ffmpeg (OGG/Opus для Telegram sendVoice).

piper CLI використано навмисно замість Python-API: API piper-tts змінюється між
версіями, а CLI стабільний (`piper -m voice.onnx -f out.wav`, текст у stdin).
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from .config import settings

logger = logging.getLogger("jarvis.tts")


def clean_text(text: str, max_chars: int) -> str:
    """Схлопує пробіли й обрізає до max_chars (голосове не має бути нескінченним)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:max_chars]


def _synth_blocking(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "out.wav"
        ogg = Path(td) / "out.ogg"
        subprocess.run(
            ["piper", "-m", settings.voice_path, "-f", str(wav)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=settings.synth_timeout,
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libopus", "-b:a", "32k", str(ogg)],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return ogg.read_bytes()


async def synthesize(text: str) -> bytes:
    """Текст → OGG/Opus байти. Кидає ValueError на порожній текст, CalledProcessError на збій."""
    clean = clean_text(text, settings.max_chars)
    if not clean:
        raise ValueError("empty text")
    return await asyncio.to_thread(_synth_blocking, clean)
