"""Клієнт TTS-сервісу: текст → OGG/Opus байти. Толерантний (None при помилці)."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jarvis.tts_client")


class TtsClient:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._url = f"{base_url.rstrip('/')}/tts"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def synthesize(self, text: str) -> bytes | None:
        """Повертає OGG-байти або None (тоді gateway фолбекне на текстову відповідь)."""
        try:
            resp = await self._client.post(self._url, json={"text": text})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("tts synthesize failed: %s", exc)
            return None
        return resp.content
