"""Клієнт оркестратора (n8n): Gateway → n8n webhook → (Ollama/Memory/Tools) → текст."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.orchestrator")

FALLBACK = "Вибач, зараз не можу обробити запит — оркестратор недоступний. Спробуй ще раз трохи згодом."


def extract_text(data: Any) -> str:
    """Дістає текст відповіді з різних можливих форматів n8n/Ollama."""
    if isinstance(data, str):
        return data or FALLBACK
    if isinstance(data, dict):
        for key in ("text", "reply", "message", "output", "answer", "response"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        # Ollama-подібна структура {"message": {"content": "..."}}
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    return FALLBACK


class Orchestrator:
    def __init__(self, webhook_url: str, timeout: float = 90.0) -> None:
        self._url = webhook_url
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def process(self, payload: dict[str, Any]) -> str:
        try:
            resp = await self._client.post(self._url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("orchestrator call failed: %s", exc)
            return FALLBACK
        try:
            return extract_text(resp.json())
        except ValueError:
            return resp.text or FALLBACK
