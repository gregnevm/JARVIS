"""Синтез мовлення: Coqui XTTS v2 (WAV, GPU) → ffmpeg (OGG/Opus для Telegram sendVoice)."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tts")

_model = None
_model_lock = Lock()
_synth_lock = Lock()
_resolved_device: str | None = None


def clean_text(text: str, max_chars: int) -> str:
    """Схлопує пробіли й обрізає до max_chars (голосове не має бути нескінченним)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:max_chars]


def resolved_device() -> str:
    """Поточний device (cuda/cpu), з кешем після першого resolve."""
    global _resolved_device
    if _resolved_device is not None:
        return _resolved_device
    want = settings.device.strip().lower()
    if want == "auto":
        import torch

        _resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        _resolved_device = want
    return _resolved_device


def _get_model() -> Any:
    global _model, _resolved_device
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from TTS.api import TTS

        device = resolved_device()
        logger.info("Loading XTTS v2 (%s) on %s...", settings.model_name, device)
        tts = TTS(settings.model_name)
        if device == "cuda":
            try:
                tts = tts.to("cuda")
            except Exception:
                logger.exception("CUDA unavailable — falling back to CPU")
                _resolved_device = "cpu"
                device = "cpu"
        _model = tts
        logger.info("XTTS v2 ready on %s", device)
        return _model


def preload_model() -> None:
    """Завантажити модель на старті (перший /tts без 30–60с cold start)."""
    ref = Path(settings.speaker_wav)
    if not ref.is_file():
        raise FileNotFoundError(f"speaker reference missing: {ref}")
    _get_model()


def _synth_blocking(text: str) -> bytes:
    with _synth_lock:
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "out.wav"
            ogg = Path(td) / "out.ogg"
            model = _get_model()
            model.tts_to_file(
                text=text,
                file_path=str(wav),
                speaker_wav=settings.speaker_wav,
                language=settings.language,
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
    return await asyncio.wait_for(
        asyncio.to_thread(_synth_blocking, clean),
        timeout=settings.synth_timeout,
    )
