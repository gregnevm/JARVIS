from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis_core.pipeline.base import Handler
from jarvis_core.pipeline.types import AgentRequest, AgentResponse

_MAX_TEXT = 8000
_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior)\s+instructions|system\s*:\s*|<\s*/?\s*system)",
    re.IGNORECASE,
)


class SafetyHandler(Handler):
    async def _process(self, req: AgentRequest) -> AgentResponse | None:
        text = (req.text or "").strip()
        if not text:
            req.blocked = True
            return AgentResponse(text="Надішли текст або голосове повідомлення.", mode="blocked")
        if len(text) > _MAX_TEXT:
            req.text = text[:_MAX_TEXT]
        if _INJECTION_RE.search(text):
            req.blocked = True
            return AgentResponse(
                text="Запит виглядає небезпечно — переформулюй, будь ласка.",
                mode="blocked",
            )
        return None


class ModeRouterHandler(Handler):
    """Визначає chat/agent до інференсу (евристика з agent.py)."""

    def __init__(self, decide_mode: Callable[[str, str], str]) -> None:
        self._decide = decide_mode

    async def _process(self, req: AgentRequest) -> AgentResponse | None:
        req.mode = self._decide(req.text, req.agent_mode)
        return None


class InferenceHandler(Handler):
    def __init__(
        self,
        run_agent: Callable[[int, str, str], Awaitable[dict[str, Any]]],
    ) -> None:
        self._run = run_agent

    async def _process(self, req: AgentRequest) -> AgentResponse | None:
        if req.blocked:
            return None
        data = await self._run(req.user_id, req.text, req.mode)
        return AgentResponse(
            text=str(data.get("text", "")),
            mode=str(data.get("mode", req.mode)),
            iters=int(data.get("iters", 0)),
            extra={k: v for k, v in data.items() if k not in ("text", "mode", "iters")},
        )


def build_agent_pipeline(
    decide_mode: Callable[[str, str], str],
    run_agent: Callable[[int, str, str], Awaitable[dict[str, Any]]],
) -> Handler:
    """Cache → Safety → ModeRouter → Inference (DESIGN §5.3; cache — у gateway/redis)."""
    safety = SafetyHandler()
    router = ModeRouterHandler(decide_mode)
    inference = InferenceHandler(run_agent)
    safety.set_next(router).set_next(inference)
    return safety
