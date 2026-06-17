from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from jarvis_core.pipeline.base import Handler
from jarvis_core.pipeline.handlers import screen_text
from jarvis_core.pipeline.types import AgentRequest, AgentResponse

StreamProvider = Callable[[int, str, str | None], AsyncIterator[dict[str, Any]]]


class JARVIS:
    """Facade — єдина точка входу для агент-лупа (DESIGN §5.2).

    Обидва шляхи входять сюди: блокуючий `chat()` (через pipeline-ланцюг
    Safety→ModeRouter→Inference) і `chat_stream()` (R2 — той самий safety-скрин,
    що й SafetyHandler, далі інжектований stream-runner). Раніше стрім обходив
    facade напряму через `agent.run_stream` у роуті — тепер ні.
    """

    def __init__(
        self,
        pipeline: Handler,
        get_agent_mode: Callable[[], str],
        status_provider: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        stream_provider: StreamProvider | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._get_mode = get_agent_mode
        self._status = status_provider
        self._stream = stream_provider

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

    async def chat_stream(
        self,
        user_id: int,
        text: str,
        *,
        mode: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу через facade (R2). Safety-скрин той самий, що в
        pipeline (SafetyHandler); далі — інжектований stream-runner (`agent.run_stream`).
        Блокування віддається фінальною подією `done`, як і в звичайному завершенні."""
        safe, block = screen_text(text)
        if block is not None:
            yield {"done": True, "mode": block.mode, "iters": 0, "text": block.text}
            return
        if self._stream is None:
            yield {
                "done": True,
                "mode": "error",
                "iters": 0,
                "text": "Стрімінг недоступний — спробуй ще раз.",
            }
            return
        hint = mode if mode and mode != "auto" else None
        async for ev in self._stream(user_id, safe or text, hint):
            yield ev

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
