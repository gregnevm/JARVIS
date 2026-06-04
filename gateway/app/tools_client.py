"""Клієнт Tools-сервісу: Gateway → POST /agent (DESIGN — агент-луп у Python, без n8n)."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger("jarvis.gateway.tools")

FALLBACK = "Вибач, зараз не можу обробити запит — агент недоступний. Спробуй ще раз трохи згодом."


def extract_text(data: Any) -> str:
    """Дістає текст відповіді з JSON Tools / legacy n8n-форматів."""
    if isinstance(data, str):
        return data or FALLBACK
    if isinstance(data, dict):
        for key in ("text", "reply", "message", "output", "answer", "response"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    return FALLBACK


class ToolsClient:
    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        base = base_url.rstrip("/")
        self._base = base
        self._url = f"{base}/agent"
        self._stream_url = f"{base}/agent/stream"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу (NDJSON) з /agent/stream. HTTP-помилки кидає назовні
        (виклик робить фолбек). Невалідні рядки тихо пропускаємо."""
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return
        body = {"user_id": int(user_id), "text": text}
        async with self._client.stream("POST", self._stream_url, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj

    async def process(self, payload: dict[str, Any]) -> str:
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return FALLBACK
        body = {"user_id": int(user_id), "text": text}
        try:
            resp = await self._client.post(self._url, json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("tools /agent failed: %s", exc)
            return FALLBACK
        try:
            return extract_text(resp.json())
        except ValueError:
            return resp.text or FALLBACK

    async def confirm_computer(self, user_id: int, code: str) -> str:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/confirm",
                json={"user_id": int(user_id), "code": code},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("result"), str):
                return data["result"]
        except httpx.HTTPError as exc:
            logger.error("tools /computer/confirm failed: %s", exc)
            return "Не вдалося виконати дію — tools недоступний."
        return FALLBACK

    async def cancel_computer(self, user_id: int) -> None:
        try:
            await self._client.post(
                f"{self._base}/computer/cancel",
                json={"user_id": int(user_id)},
            )
        except httpx.HTTPError as exc:
            logger.error("tools /computer/cancel failed: %s", exc)
