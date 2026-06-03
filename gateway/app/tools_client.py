"""Клієнт Tools-сервісу: Gateway → POST /agent (DESIGN — агент-луп у Python, без n8n)."""
from __future__ import annotations

import logging
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
        self._url = f"{base_url.rstrip('/')}/agent"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

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
