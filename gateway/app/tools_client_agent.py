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

    async def code_plan(self, user_id: int, text: str) -> dict[str, Any]:
        """Code-specific план із file-targets (CA-4.1) для Platform Coding tab."""
        resp = await self._request(
            "POST", "/agent/code/plan",
            json={"user_id": int(user_id), "text": text},
            log_label="code plan",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def code_review(self, user_id: int, diff: str, context: str = "") -> dict[str, Any]:
        """Self-review unified diff (CA-5.1) — diff-viewer Platform Coding tab."""
        resp = await self._request(
            "POST", "/agent/code/review",
            json={"user_id": int(user_id), "diff": diff, "context": context},
            log_label="code review",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def repo_tree(self, user_id: int, path: str = "", max_depth: int = 3) -> dict[str, Any]:
        """Дерево файлів репо (CA-2.1) для Platform Coding tab. Вимкнено → текст у `tree`."""
        resp = await self._request(
            "POST", "/coding/repo_tree",
            json={"user_id": int(user_id), "path": path, "max_depth": max_depth},
            log_label="repo tree",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def create_coding_job(
        self,
        user_id: int,
        exe: str,
        *,
        args: list[str] | None = None,
        path: str = "",
        task: str = "",
        max_rounds: int = 0,
    ) -> dict[str, Any]:
        """Створює background coding_task job (CA-5.3) — виконавець: `/agent/code/fix`."""
        resp = await self._request(
            "POST", "/bgjobs",
            json={
                "user_id": int(user_id),
                "job_type": "coding_task",
                "exe": exe,
                "args": list(args or []),
                "path": path,
                "text": task,
                "max_rounds": max_rounds,
            },
            log_label="create coding job",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def run_coding_task(
        self,
        job_id: str,
        user_id: int,
        *,
        exe: str,
        args: list[str] | None = None,
        path: str = "",
        task: str = "",
        max_rounds: int = 0,
    ) -> dict[str, Any]:
        """Виконує coding_task через `/agent/code/fix` (fix_tests). Headless: `no_confirm=True`
        — застосування правок гейтиться політикою `CODING_HEADLESS_APPLY` на tools-боці."""
        resp = await self._request(
            "POST", "/agent/code/fix",
            json={
                "user_id": int(user_id),
                "exe": exe,
                "args": list(args or []),
                "path": path,
                "task": task,
                "max_rounds": max_rounds or None,
                "no_confirm": True,
            },
            timeout=900.0,
            log_label=f"run coding task {job_id}",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}
