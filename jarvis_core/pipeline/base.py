from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis_core.pipeline.types import AgentRequest, AgentResponse


class Handler(ABC):
    def __init__(self) -> None:
        self._next: Handler | None = None

    def set_next(self, handler: Handler) -> Handler:
        self._next = handler
        return handler

    async def handle(self, req: AgentRequest) -> AgentResponse:
        out = await self._process(req)
        if out is not None:
            return out
        if self._next is None:
            return AgentResponse(text="", mode=req.mode or "unknown")
        return await self._next.handle(req)

    @abstractmethod
    async def _process(self, req: AgentRequest) -> AgentResponse | None:
        """None — передати далі по ланцюгу."""
