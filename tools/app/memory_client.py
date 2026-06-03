"""Async-клієнт Memory service (RAG-контекст + збереження історії).

Усі помилки толеруються: памʼять — не критичний шлях, агент має працювати й без неї.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.tools.memory")


class MemoryClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, user_id: int, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        try:
            resp = await self._client.post(
                f"{self._base}/search",
                json={"user_id": user_id, "query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            return list(resp.json().get("results", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory search failed: %s", exc)
            return []

    async def store(self, user_id: int, content: str, role: str = "user") -> None:
        try:
            resp = await self._client.post(
                f"{self._base}/store",
                json={"user_id": user_id, "content": content, "role": role},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("memory store failed: %s", exc)
