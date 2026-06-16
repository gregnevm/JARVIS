"""ToolsClient · домен Agent (R3): /agent + /agent/stream."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .tools_client_base import FALLBACK, ToolsClientBase, extract_text, logger


class AgentMixin(ToolsClientBase):
    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу (NDJSON) з /agent/stream. HTTP-помилки кидає назовні
        (виклик робить фолбек). Невалідні рядки тихо пропускаємо."""
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return
        body = {"user_id": int(user_id), "text": text}
        mode = payload.get("mode")
        if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
            body["mode"] = mode.strip().lower()
        async with self._client.stream(
            "POST", self._stream_url, json=body, headers=self._extra_headers(payload)
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj

    async def process(self, payload: dict[str, Any]) -> str:
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return FALLBACK
        body = {"user_id": int(user_id), "text": text}
        mode = payload.get("mode")
        if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
            body["mode"] = mode.strip().lower()
        try:
            resp = await self._client.post(
                self._url, json=body, headers=self._extra_headers(payload)
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("tools /agent failed: %s", exc)
            return FALLBACK
        try:
            return extract_text(resp.json())
        except ValueError:
            return resp.text or FALLBACK
