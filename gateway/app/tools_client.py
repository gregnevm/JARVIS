"""Клієнт Tools-сервісу: Gateway → POST /agent (DESIGN — агент-луп у Python, без n8n)."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

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


class ToolsClient:
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

    async def confirm_computer(self, user_id: int, code: str) -> tuple[str, str]:
        """Повертає (result, origin_user_text)."""
        try:
            resp = await self._client.post(
                f"{self._base}/computer/confirm",
                json={"user_id": int(user_id), "code": code},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("result"), str):
                origin = str(data.get("origin") or "")
                return data["result"], origin
        except httpx.HTTPError as exc:
            logger.error("tools /computer/confirm failed: %s", exc)
            return "Не вдалося виконати дію — tools недоступний.", ""
        return FALLBACK, ""

    async def cancel_computer(self, user_id: int) -> None:
        try:
            await self._client.post(
                f"{self._base}/computer/cancel",
                json={"user_id": int(user_id)},
            )
        except httpx.HTTPError as exc:
            logger.error("tools /computer/cancel failed: %s", exc)

    async def capture_screenshot(self, user_id: int) -> str:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/screenshot",
                json={"user_id": int(user_id)},
            )
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            logger.error("tools /computer/screenshot failed: %s", exc)
            return "Не вдалося зняти скріншот — перевір host-agent на хості (порт 8400)."

    async def pull_file(self, user_id: int, path: str) -> dict[str, Any]:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/file/pull",
                json={"user_id": int(user_id), "path": path},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "invalid response"}
        except httpx.HTTPError as exc:
            logger.error("tools file pull failed: %s", exc)
            return {"error": str(exc)}

    async def push_file(self, user_id: int, path: str, data_b64: str) -> dict[str, Any]:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/file/push",
                json={"user_id": int(user_id), "path": path, "data_b64": data_b64},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def clipboard_read(self, user_id: int) -> str:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/clipboard/read",
                json={"user_id": int(user_id)},
            )
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"Clipboard недоступний: {exc}"

    async def see_screen(self, user_id: int, question: str = "") -> str:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/see",
                json={"user_id": int(user_id), "question": question},
            )
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"See screen failed: {exc}"

    async def list_macros(self) -> dict[str, Any]:
        try:
            resp = await self._client.get(f"{self._base}/computer/macros")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {"macros": []}

    async def run_macro(self, user_id: int, name: str) -> str:
        try:
            resp = await self._client.post(
                f"{self._base}/computer/macro/run",
                json={"user_id": int(user_id), "name": name},
            )
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"Macro failed: {exc}"

    async def grant_trust(self, user_id: int) -> None:
        try:
            await self._client.post(
                f"{self._base}/computer/trust",
                json={"user_id": int(user_id)},
            )
        except httpx.HTTPError as exc:
            logger.error("grant trust failed: %s", exc)

    async def remote_status(self, user_id: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        try:
            r = await self._client.get(
                f"{self._base}/computer/pending", params={"user_id": user_id}
            )
            out["pending"] = r.json() if r.status_code == 200 else {}
            r2 = await self._client.get(f"{self._base}/computer/audit", params={"limit": 20})
            r3 = await self._client.get(f"{self._base}/computer/learned")
            out["learned"] = r3.json() if r3.status_code == 200 else {}
            out["audit"] = r2.json() if r2.status_code == 200 else {}
        except httpx.HTTPError:
            pass
        return out

    async def list_tasks(self, user_id: int) -> str:
        try:
            resp = await self._client.get(f"{self._base}/tasks", params={"user_id": user_id})
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError:
            return "Tasks недоступні."

    async def cancel_tasks(self, user_id: int) -> None:
        try:
            await self._client.delete(f"{self._base}/tasks", params={"user_id": user_id})
        except httpx.HTTPError:
            pass

    async def reminders_ics(self, user_id: int) -> bytes:
        try:
            resp = await self._client.get(
                f"{self._base}/reminders/ics", params={"user_id": user_id}
            )
            if resp.status_code == 404:
                return b""
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            logger.error("reminders ics failed: %s", exc)
            return b""

    async def export_dataset(self, user_id: int | None = None) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {}
            if user_id is not None:
                params["user_id"] = int(user_id)
            resp = await self._client.post(
                f"{self._base}/dataset/export/sharegpt", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            logger.error("dataset export failed: %s", exc)
            return {"error": str(exc)}

    async def dataset_stats(self, user_id: int | None = None) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {}
            if user_id is not None:
                params["user_id"] = int(user_id)
            resp = await self._client.get(f"{self._base}/dataset/stats", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def due_jobs(self) -> list[dict[str, Any]]:
        try:
            resp = await self._client.get(f"{self._base}/jobs/due")
            resp.raise_for_status()
            data = resp.json()
            return data.get("jobs") if isinstance(data, dict) else []
        except httpx.HTTPError:
            return []
