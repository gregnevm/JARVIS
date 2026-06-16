"""Спільна база ToolsClient (R3): HTTP-плумбінг + extract_text.

ToolsClient розбито на доменні mixin-и (agent/computer/jobs/orchestrator), що
успадковують цю базу й ділять один `_request`/`_client`. Публічний клас-агрегатор
лишається в `tools_client.py` для зворотної сумісності.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .tools_client_http import tools_request

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


class ToolsClientBase:
    """HTTP-плумбінг, спільний для всіх доменних mixin-ів."""

    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        base = base_url.rstrip("/")
        self._base = base
        self._url = f"{base}/agent"
        self._stream_url = f"{base}/agent/stream"
        self._client = httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _extra_headers(payload: dict[str, Any]) -> dict[str, str]:
        rid = payload.get("request_id")
        if isinstance(rid, str) and rid.strip():
            return {"X-Request-ID": rid.strip()}
        return {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        log_label: str = "",
    ) -> httpx.Response | None:
        return await tools_request(
            self._client,
            self._base,
            method,
            path,
            json=json,
            params=params,
            timeout=timeout,
            log_label=log_label,
        )
