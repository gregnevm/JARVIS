"""HTTP-клієнти до Tools / Twin для Telegram-дашборду.

R2 «Тонкий шлюз»: HTTP-плумбінг делеговано `jarvis_core.service_client.call`
(довгоживучі клієнти лишаються — реюз з'єднань), фолбек-семантика методів 1:1.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from jarvis_core.service_client import ServiceError, call

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
        try:
            out = await call(
                self._tools, "GET", "/dashboard",
                timeout=None, retries=2, retry_backoff=0.0,
                retry_statuses=range(400, 600),  # історична семантика: ретрай будь-якого фейлу
                service="tools", client=self._dash_client,
            )
        except ServiceError as exc:
            logger.error("dashboard failed: %s", exc)
            return {"error": "tools_unreachable"}
        return out if isinstance(out, dict) else {}

    async def set_mode(self, mode: str) -> dict[str, Any]:
        try:
            out = await call(
                self._tools, "POST", "/mode",
                json={"mode": mode}, timeout=None, service="tools", client=self._client,
            )
        except ServiceError as exc:
            logger.error("set_mode failed: %s", exc)
            return {"error": str(exc)}
        return out if isinstance(out, dict) else {}

    async def twin_status(self) -> dict[str, Any]:
        try:
            out = await call(
                self._twin, "GET", "/status",
                timeout=None, service="twin", client=self._client,
            )
        except ServiceError:
            return {}
        return out if isinstance(out, dict) else {}

    async def twin_lora_versions(self) -> dict[str, Any]:
        try:
            out = await call(
                self._twin, "GET", "/registry/versions",
                timeout=None, service="twin", client=self._client,
            )
        except ServiceError as exc:
            logger.error("twin versions failed: %s", exc)
            return {"versions": [], "error": str(exc)}
        return out if isinstance(out, dict) else {}

    async def tools_deploy_lora(self) -> dict[str, Any]:
        try:
            out = await call(
                self._tools, "POST", "/lora/deploy",
                json={}, timeout=200.0, service="tools", client=self._client,
            )
        except ServiceError as exc:
            logger.error("lora deploy failed: %s", exc)
            # ServiceError.detail уже несе memory-style detail (json detail або text[:200]).
            return {"ok": False, "error": exc.detail or str(exc)}
        return out if isinstance(out, dict) else {}

    async def twin_promote_lora(self, version: str, *, deploy: bool = True) -> dict[str, Any]:
        try:
            out = await call(
                self._twin, "POST", f"/registry/lora/{version}/promote",
                timeout=None, service="twin", client=self._client,
            )
        except ServiceError as exc:
            logger.error("twin promote failed: %s", exc)
            return {"error": str(exc)}
        result = out if isinstance(out, dict) else {}
        if deploy:
            result["ollama"] = await self.tools_deploy_lora()
        return result

    async def twin_rollback_lora(self, n: int = 1, *, deploy: bool = True) -> dict[str, Any]:
        try:
            out = await call(
                self._twin, "POST", "/registry/lora/rollback",
                params={"n": n}, timeout=None, service="twin", client=self._client,
            )
        except ServiceError as exc:
            logger.error("twin rollback failed: %s", exc)
            return {"error": str(exc)}
        result = out if isinstance(out, dict) else {}
        if deploy:
            result["ollama"] = await self.tools_deploy_lora()
        return result

    async def reset_mode(self) -> dict[str, Any]:
        try:
            out = await call(
                self._tools, "DELETE", "/mode",
                timeout=None, service="tools", client=self._client,
            )
        except ServiceError as exc:
            logger.error("reset_mode failed: %s", exc)
            return {"error": str(exc)}
        return out if isinstance(out, dict) else {}
