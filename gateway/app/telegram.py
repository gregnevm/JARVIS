"""Тонкий асинхронний клієнт Telegram Bot API."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.telegram")

TELEGRAM_MAX_LEN = 4096


def split_message(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Розбиває довгий текст на частини <= limit, по можливості на межі рядків."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        # Один рядок довший за ліміт — ріжемо жорстко.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


class TelegramClient:
    def __init__(self, token: str, api_base: str = "https://api.telegram.org") -> None:
        base = api_base.rstrip("/")
        self._api = f"{base}/bot{token}"
        self._files = f"{base}/file/bot{token}"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(f"{self._api}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str | None = None
    ) -> None:
        for chunk in split_message(text):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            try:
                await self._call("sendMessage", payload)
            except httpx.HTTPError as exc:
                logger.error("sendMessage failed: %s", exc)

    async def get_file_path(self, file_id: str) -> str | None:
        data = await self._call("getFile", {"file_id": file_id})
        result = data.get("result") or {}
        return result.get("file_path")

    async def download_file(self, file_path: str) -> bytes:
        resp = await self._client.get(f"{self._files}/{file_path}")
        resp.raise_for_status()
        return resp.content
