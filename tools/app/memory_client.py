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

    async def search_context(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
        tags: list[str] | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Ретрив паспортів контексту (P9/P10) — для інжекту в промпт. Толерантний."""
        try:
            resp = await self._client.post(
                f"{self._base}/context/search",
                json={"user_id": user_id, "query": query, "top_k": top_k,
                      "tags": tags, "since": since},
            )
            resp.raise_for_status()
            return list(resp.json().get("results", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory context search failed: %s", exc)
            return []

    # --- Context Passport порт (для context-jobs, jarvis_core.passport.ContextStore) ---
    async def context_pending(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        try:
            resp = await self._client.post(
                f"{self._base}/context/pending", json={"user_id": user_id, "limit": limit}
            )
            resp.raise_for_status()
            return list(resp.json().get("events", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("context pending failed: %s", exc)
            return []

    async def context_recent(
        self,
        user_id: int,
        limit: int,
        kind: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            resp = await self._client.post(
                f"{self._base}/context/recent",
                json={"user_id": user_id, "limit": limit, "kind": kind, "tags": tags},
            )
            resp.raise_for_status()
            return list(resp.json().get("events", []))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("context recent failed: %s", exc)
            return []

    async def context_update(
        self, event_db_id: int, user_id: int, summary: str, tags: list[str], kind: str
    ) -> dict[str, Any]:
        try:
            resp = await self._client.post(
                f"{self._base}/context/update",
                json={"id": event_db_id, "user_id": user_id, "summary": summary,
                      "tags": tags, "kind": kind},
            )
            resp.raise_for_status()
            return dict(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("context update failed: %s", exc)
            return {"ok": False}

    async def context_ingest(self, store: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(f"{self._base}/context/ingest", json=store)
            resp.raise_for_status()
            return dict(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("context ingest failed: %s", exc)
            return {"inserted": False}

    async def context_purge(
        self, user_id: int, before: str | None = None, kind: str | None = None
    ) -> int:
        try:
            resp = await self._client.post(
                f"{self._base}/context/purge",
                json={"user_id": user_id, "before": before, "kind": kind},
            )
            resp.raise_for_status()
            return int(resp.json().get("deleted", 0))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("context purge failed: %s", exc)
            return 0

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

    # --- Стовп D: team-ecosystem proxy (граф / групи) ------------------------

    async def team_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.get(f"{self._base}{path}", params=params or {})
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory team_get %s failed: %s", path, exc)
            return {}

    async def team_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(f"{self._base}{path}", json=body)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory team_post %s failed: %s", path, exc)
            return {"error": str(exc)}

    async def team_put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.put(f"{self._base}{path}", json=body)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("memory team_put %s failed: %s", path, exc)
            return {"error": str(exc)}
