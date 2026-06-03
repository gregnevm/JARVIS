from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

import httpx

from jarvis_core.llm.exceptions import CircuitOpen
from jarvis_core.llm.interface import LLMInterface

logger = logging.getLogger("jarvis_core.llm.chat")


class ChatBackend(Protocol):
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int = 1024,
    ) -> dict[str, Any]: ...


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Зводить chat messages у один prompt для LLMInterface.generate."""
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role", "user"))
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role.upper()}: {content}")
    return "\n".join(parts)


class LLMChatBackend:
    """Міст sync LLMInterface → async chat (без tool calling)."""

    def __init__(self, llm: LLMInterface, default_model: str = "local") -> None:
        self._llm = llm
        self._default_model = default_model

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int = 1024,
    ) -> dict[str, Any]:
        if tools:
            raise ValueError("LLMChatBackend does not support tool calling")
        prompt = messages_to_prompt(messages)
        text = await asyncio.to_thread(self._llm.generate, prompt, num_predict)
        return {"role": "assistant", "content": text.strip()}


class OllamaChatBackend:
    """Ollama /api/chat + circuit breaker (tool calling)."""

    def __init__(
        self,
        host: str,
        timeout: float = 180.0,
        fail_threshold: int = 3,
        cooldown: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = f"{host.rstrip('/')}/api/chat"
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._threshold = max(1, fail_threshold)
        self._cooldown = cooldown
        self._fails = 0
        self._open_until = 0.0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _trip(self) -> None:
        self._fails += 1
        if self._fails >= self._threshold:
            self._open_until = time.monotonic() + self._cooldown
            self._fails = 0
            logger.warning("Ollama circuit OPEN for %.0fs", self._cooldown)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int = 1024,
    ) -> dict[str, Any]:
        remaining = self._open_until - time.monotonic()
        if remaining > 0:
            raise CircuitOpen(f"Ollama circuit open ~{int(remaining)}s")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": num_predict},
        }
        if tools:
            payload["tools"] = tools
        try:
            resp = await self._client.post(self._url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._trip()
            raise
        msg = data.get("message")
        if not isinstance(msg, dict):
            self._trip()
            raise ValueError(f"unexpected ollama response: {data!r}")
        self._fails = 0
        return msg


class CompositeChatBackend:
    """Tool-луп через Ollama chat; простий чат — через LLMInterface (DESIGN bridge)."""

    def __init__(self, ollama: OllamaChatBackend, llm: LLMInterface) -> None:
        self._ollama = ollama
        self._llm_chat = LLMChatBackend(llm)

    async def aclose(self) -> None:
        await self._ollama.aclose()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int = 1024,
    ) -> dict[str, Any]:
        if tools:
            return await self._ollama.chat(model, messages, tools=tools, num_predict=num_predict)
        return await self._llm_chat.chat(model, messages, tools=None, num_predict=num_predict)
