"""Клієнт Whisper STT (onerahmet/openai-whisper-asr-webservice).

Сервіс приймає аудіо як multipart `audio_file` на `/asr` і повертає транскрипт.
encode=true → всередині ffmpeg декодує OGG/Opus із Telegram у потрібний формат.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jarvis.whisper")


class WhisperClient:
    def __init__(self, base_url: str, language: str = "", timeout: float = 120.0) -> None:
        self._url = f"{base_url.rstrip('/')}/asr"
        self._language = language.strip()
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        """Аудіо → текст. Повертає '' при помилці або порожньому розпізнаванні."""
        params: dict[str, str] = {"task": "transcribe", "output": "txt", "encode": "true"}
        if self._language:
            params["language"] = self._language
        try:
            resp = await self._client.post(
                self._url,
                params=params,
                files={"audio_file": (filename, audio, "application/octet-stream")},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("whisper transcribe failed: %s", exc)
            return ""
        return resp.text.strip()
