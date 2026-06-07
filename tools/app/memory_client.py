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

    async def search(
        self, user_id: int, query: str, top_k: int = 5, project_id: int | None = None
    ) -> list[dict[str, Any]]:
        try:
            resp = await self._client.post(
                f"{self._base}/search",
                json={"user_id": user_id, "query": query, "top_k": top_k, "project_id": project_id},
            )
            resp.raise_for_status()
            return list(resp.json().get("results", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory search failed: %s", exc)
            return []

    async def store(
        self, user_id: int, content: str, role: str = "user", project_id: int | None = None
    ) -> None:
        try:
            resp = await self._client.post(
                f"{self._base}/store",
                json={"user_id": user_id, "content": content, "role": role, "project_id": project_id},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("memory store failed: %s", exc)

    async def get_project(
        self, user_id: int, project_id: int, *, include_content: bool = False
    ) -> dict[str, Any] | None:
        try:
            params: dict[str, Any] = {"user_id": user_id}
            if include_content:
                params["include_content"] = "true"
            resp = await self._client.get(
                f"{self._base}/projects/{int(project_id)}", params=params
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory get_project failed: %s", exc)
            return None

    async def history(self, user_id: int, limit: int = 12) -> list[dict[str, Any]]:
        try:
            resp = await self._client.post(
                f"{self._base}/history",
                json={"user_id": user_id, "limit": limit},
            )
            resp.raise_for_status()
            return list(resp.json().get("messages", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory history failed: %s", exc)
            return []

    async def list_sessions(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        try:
            resp = await self._client.get(
                f"{self._base}/sessions",
                params={"user_id": user_id, "limit": limit},
            )
            resp.raise_for_status()
            return list(resp.json().get("sessions", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory sessions failed: %s", exc)
            return []
