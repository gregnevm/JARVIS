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
        # Швидкий клієнт для дашборда — не чекаємо 15с на кожен полінг Mini App.
        self._dash_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.0, read=8.0, write=5.0, pool=2.0)
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._dash_client.aclose()

    async def dashboard(self) -> dict[str, Any]:
        url = f"{self._tools}/dashboard"
        last_exc: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                r = await self._dash_client.get(url)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < 2:
                    logger.debug("dashboard retry %s: %s", attempt + 1, exc)
        logger.error("dashboard failed: %s", last_exc)
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
