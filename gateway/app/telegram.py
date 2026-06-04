"""Тонкий асинхронний клієнт Telegram Bot API."""
from __future__ import annotations

import logging
import os
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

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
        allowed_updates: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        try:
            await self._call("setWebhook", payload)
        except httpx.HTTPError as exc:
            logger.error("setWebhook failed: %s", exc)

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
        message_thread_id: int | None = None,
    ) -> None:
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if message_thread_id is not None:
                payload["message_thread_id"] = message_thread_id
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

    async def send_message_id(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> int | None:
        """Шле одне (нерозбите) повідомлення і повертає message_id — для стрім-плейсхолдера."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:TELEGRAM_MAX_LEN]}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            data = await self._call("sendMessage", payload)
        except httpx.HTTPError as exc:
            logger.error("sendMessage(id) failed: %s", exc)
            return None
        mid = (data.get("result") or {}).get("message_id")
        return int(mid) if isinstance(mid, int) else None

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        message_thread_id: int | None = None,
    ) -> None:
        """editMessageText. 'message is not modified' та інші помилки лише логуються."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:TELEGRAM_MAX_LEN],
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            await self._call("editMessageText", payload)
        except httpx.HTTPError as exc:
            logger.debug("editMessageText failed: %s", exc)

    async def set_message_reaction(
        self, chat_id: int, message_id: int, emoji: str, is_big: bool = False
    ) -> bool:
        """Ставить емодзі-реакцію на повідомлення (setMessageReaction)."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
            "is_big": is_big,
        }
        try:
            await self._call("setMessageReaction", payload)
            return True
        except httpx.HTTPError as exc:
            logger.debug("setMessageReaction failed: %s", exc)
            return False

    async def answer_inline_query(
        self,
        inline_query_id: str,
        results: list[dict[str, Any]],
        cache_time: int = 0,
    ) -> None:
        """Відповідь на inline-запит (@bot ...) списком результатів."""
        try:
            await self._call(
                "answerInlineQuery",
                {
                    "inline_query_id": inline_query_id,
                    "results": results,
                    "cache_time": cache_time,
                },
            )
        except httpx.HTTPError as exc:
            logger.error("answerInlineQuery failed: %s", exc)

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

    async def set_my_commands(self, commands: list[dict[str, str]]) -> None:
        """Меню команд BotFather (кнопка «/» у полі вводу)."""
        try:
            await self._call("setMyCommands", {"commands": commands})
        except httpx.HTTPError as exc:
            logger.error("setMyCommands failed: %s", exc)

    async def set_my_description(self, description: str) -> None:
        try:
            await self._call("setMyDescription", {"description": description[:512]})
        except httpx.HTTPError as exc:
            logger.error("setMyDescription failed: %s", exc)

    async def set_my_short_description(self, description: str) -> None:
        try:
            await self._call("setMyShortDescription", {"description": description[:120]})
        except httpx.HTTPError as exc:
            logger.error("setMyShortDescription failed: %s", exc)

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

    # ----------------------------------------------------------------------- #
    # Вихідні медіа: фото/документ/відео/аудіо/анімація/стікер/локація.
    # Джерело (src) може бути: http(s) URL, локальний шлях (multipart-аплоуд)
    # або Telegram file_id. Усе визначаємо автоматично у _send_media().
    # ----------------------------------------------------------------------- #
    async def _send_media(
        self,
        method: str,
        field: str,
        chat_id: int,
        src: str | bytes,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> bool:
        """Універсальний відправник медіа. True/False — успіх. Помилки логуються."""
        data: dict[str, str] = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption[:1024]
            if parse_mode:
                data["parse_mode"] = parse_mode
        try:
            if isinstance(src, bytes):
                files = {field: (f"{field}.bin", src)}
                resp = await self._client.post(f"{self._api}/{method}", data=data, files=files)
            elif isinstance(src, str) and src.startswith(("http://", "https://")):
                resp = await self._client.post(
                    f"{self._api}/{method}", json={**data, field: src}
                )
            elif isinstance(src, str) and os.path.isfile(src):
                with open(src, "rb") as fh:
                    files = {field: (os.path.basename(src), fh.read())}
                resp = await self._client.post(f"{self._api}/{method}", data=data, files=files)
            elif isinstance(src, str) and (
                src.startswith(("/", "./")) or "\\" in src or src.endswith((".png", ".jpg", ".jpeg"))
            ):
                logger.error("%s: локальний файл не знайдено: %s", method, src)
                return False
            else:
                # Інакше трактуємо як file_id (вже завантажений у Telegram файл).
                resp = await self._client.post(
                    f"{self._api}/{method}", json={**data, field: src}
                )
            resp.raise_for_status()
            return True
        except (httpx.HTTPError, OSError) as exc:
            logger.error("%s failed: %s", method, exc)
            return False

    async def send_photo(
        self, chat_id: int, src: str | bytes, caption: str | None = None
    ) -> bool:
        return await self._send_media("sendPhoto", "photo", chat_id, src, caption)

    async def send_document(
        self, chat_id: int, src: str | bytes, caption: str | None = None
    ) -> bool:
        return await self._send_media("sendDocument", "document", chat_id, src, caption)

    async def send_video(
        self, chat_id: int, src: str | bytes, caption: str | None = None
    ) -> bool:
        return await self._send_media("sendVideo", "video", chat_id, src, caption)

    async def send_audio(
        self, chat_id: int, src: str | bytes, caption: str | None = None
    ) -> bool:
        return await self._send_media("sendAudio", "audio", chat_id, src, caption)

    async def send_animation(
        self, chat_id: int, src: str | bytes, caption: str | None = None
    ) -> bool:
        return await self._send_media("sendAnimation", "animation", chat_id, src, caption)

    async def send_sticker(self, chat_id: int, src: str) -> bool:
        return await self._send_media("sendSticker", "sticker", chat_id, src)

    async def send_media_group(
        self,
        chat_id: int,
        photos: list[tuple[str, str | None]],
        *,
        message_thread_id: int | None = None,
    ) -> None:
        """Альбом фото (2–10). Підтримує http(s) URL; інше — по одному sendPhoto."""
        media: list[dict[str, Any]] = []
        for i, (src, cap) in enumerate(photos[:10]):
            if isinstance(src, str) and src.startswith(("http://", "https://")):
                entry: dict[str, Any] = {"type": "photo", "media": src}
                if cap and i == 0:
                    entry["caption"] = cap[:1024]
                media.append(entry)
        if len(media) < 2:
            for src, cap in photos:
                await self.send_photo(chat_id, src, cap)
            return
        payload: dict[str, Any] = {"chat_id": chat_id, "media": media}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        try:
            await self._call("sendMediaGroup", payload)
        except httpx.HTTPError as exc:
            logger.warning("sendMediaGroup failed, fallback to sendPhoto: %s", exc)
            for src, cap in photos:
                await self.send_photo(chat_id, src, cap)

    async def send_location(self, chat_id: int, latitude: float, longitude: float) -> bool:
        """Надсилає геолокацію. Помилки логуються, не кидаються."""
        try:
            resp = await self._call(
                "sendLocation",
                {"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
            )
            return bool(resp.get("ok", True))
        except httpx.HTTPError as exc:
            logger.error("sendLocation failed: %s", exc)
            return False
