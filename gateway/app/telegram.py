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

    async def delete_webhook(self, drop_pending: bool = False) -> None:
        """Знімає webhook. Потрібно перед getUpdates (вони взаємовиключні)."""
        try:
            await self._call("deleteWebhook", {"drop_pending_updates": drop_pending})
        except httpx.HTTPError as exc:
            logger.error("deleteWebhook failed: %s", exc)

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Long poll getUpdates. Запит висить до `timeout` с або до першого апдейту."""
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        # read-timeout має перевищувати long-poll timeout, інакше httpx обірве сам.
        resp = await self._client.post(
            f"{self._api}/getUpdates", json=payload, timeout=timeout + 15
        )
        resp.raise_for_status()
        result = resp.json().get("result")
        return result if isinstance(result, list) else []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            try:
                await self._call("sendMessage", payload)
            except httpx.HTTPError as exc:
                logger.error("sendMessage failed: %s", exc)
                if parse_mode:
                    plain: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
                    if reply_markup and i == len(chunks) - 1:
                        plain["reply_markup"] = reply_markup
                    await self._call("sendMessage", plain)

    async def set_chat_menu_button(self, url: str, text: str = "Dashboard") -> None:
        """Реєструє кнопку-меню (зліва від поля вводу) як вхід у Mini App.

        Без chat_id ставить дефолт для всіх чатів бота. url має бути https.
        """
        try:
            await self._call(
                "setChatMenuButton",
                {"menu_button": {"type": "web_app", "text": text, "web_app": {"url": url}}},
            )
        except httpx.HTTPError as exc:
            logger.error("setChatMenuButton failed: %s", exc)

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        """Показує індикатор (typing…/record_voice). Помилки лише логуються."""
        try:
            await self._call("sendChatAction", {"chat_id": chat_id, "action": action})
        except httpx.HTTPError as exc:
            logger.debug("sendChatAction failed: %s", exc)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        try:
            await self._call("answerCallbackQuery", payload)
        except httpx.HTTPError as exc:
            logger.error("answerCallbackQuery failed: %s", exc)

    async def get_file_path(self, file_id: str) -> str | None:
        data = await self._call("getFile", {"file_id": file_id})
        result = data.get("result") or {}
        return result.get("file_path")

    async def download_file(self, file_path: str) -> bytes:
        resp = await self._client.get(f"{self._files}/{file_path}")
        resp.raise_for_status()
        return resp.content

    async def send_voice(self, chat_id: int, audio: bytes, caption: str | None = None) -> None:
        """Надсилає голосове (OGG/Opus). Помилки логуються, не кидаються."""
        data: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption[:1024]
        files = {"voice": ("voice.ogg", audio, "audio/ogg")}
        try:
            resp = await self._client.post(f"{self._api}/sendVoice", data=data, files=files)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("sendVoice failed: %s", exc)
