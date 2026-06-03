"""HTTP-клієнти до Tools / Twin для Telegram-дашборду."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.gateway.services")


class ServicesClient:
    def __init__(self, tools_url: str, twin_url: str, timeout: float = 15.0) -> None:
        self._tools = tools_url.rstrip("/")
        self._twin = twin_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def dashboard(self) -> dict[str, Any]:
        try:
            r = await self._client.get(f"{self._tools}/dashboard")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("dashboard failed: %s", exc)
            return {"error": "tools_unreachable"}

    async def set_mode(self, mode: str) -> dict[str, Any]:
        try:
            r = await self._client.post(f"{self._tools}/mode", json={"mode": mode})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("set_mode failed: %s", exc)
            return {"error": str(exc)}

    async def twin_status(self) -> dict[str, Any]:
        try:
            r = await self._client.get(f"{self._twin}/status")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return {}

    async def reset_mode(self) -> dict[str, Any]:
        try:
            r = await self._client.delete(f"{self._tools}/mode")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("reset_mode failed: %s", exc)
            return {"error": str(exc)}
