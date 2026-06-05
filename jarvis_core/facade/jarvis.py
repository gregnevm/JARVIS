from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from jarvis_core.pipeline.base import Handler
from jarvis_core.pipeline.types import AgentRequest, AgentResponse


class JARVIS:
    """Facade — єдина точка входу для агент-лупа (DESIGN §5.2)."""

    def __init__(
        self,
        pipeline: Handler,
        get_agent_mode: Callable[[], str],
        status_provider: Callable[[], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._get_mode = get_agent_mode
        self._status = status_provider

    async def chat(
        self,
        user_id: int,
        text: str,
        *,
        chat_id: int | None = None,
        source: str = "text",
        mode: str | None = None,
    ) -> dict[str, Any]:
        req = AgentRequest(
            user_id=user_id,
            text=text,
            chat_id=chat_id,
            source=source,
            agent_mode=self._get_mode(),
            mode_hint=(mode or "auto"),
        )
        resp = await self._pipeline.handle(req)
        return resp.to_dict()

    async def dashboard(self) -> dict[str, Any]:
        if self._status is None:
            return {"agent_mode": self._get_mode()}
        data = await self._status()
        data.setdefault("agent_mode", self._get_mode())
        return data

    async def set_mode(self, mode: str) -> dict[str, str]:
        mode = mode.lower().strip()
        if mode not in ("chat", "agent", "hybrid"):
            raise ValueError("mode must be chat, agent, or hybrid")
        return {"mode": mode, "status": "pending"}
