"""Тонкий async-клієнт Ollama /api/chat (tool calling) + circuit breaker.

Breaker: після N підряд помилок розмикаємось на cooldown секунд і одразу кидаємо
CircuitOpen, не чекаючи таймауту — щоб не висіти по 180с на мертвому Ollama.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("jarvis.tools.ollama")


class CircuitOpen(Exception):
    """Ollama тимчасово вважається недоступним (брейкер розімкнено)."""


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 180.0,
        fail_threshold: int = 3,
        cooldown: float = 60.0,
    ) -> None:
        self._url = f"{host.rstrip('/')}/api/chat"
        self._client = httpx.AsyncClient(timeout=timeout)
        self._threshold = max(1, fail_threshold)
        self._cooldown = cooldown
        self._fails = 0
        self._open_until = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    def _trip(self) -> None:
        self._fails += 1
        if self._fails >= self._threshold:
            self._open_until = time.monotonic() + self._cooldown
            self._fails = 0
            logger.warning("Ollama circuit OPEN for %.0fs", self._cooldown)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int = 1024,
    ) -> dict[str, Any]:
        """Повертає об'єкт message: {role, content, tool_calls?}."""
        remaining = self._open_until - time.monotonic()
        if remaining > 0:
            raise CircuitOpen(f"Ollama недоступний ще ~{int(remaining)}с")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": num_predict},
        }
        if tools:
            payload["tools"] = tools
        try:
            resp = await self._client.post(self._url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._trip()
            raise
        msg = data.get("message")
        if not isinstance(msg, dict):
            self._trip()
            raise ValueError(f"unexpected ollama response: {data!r}")
        self._fails = 0  # успіх → скидаємо лічильник
        return msg
