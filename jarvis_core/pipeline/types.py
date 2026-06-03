from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRequest:
    user_id: int
    text: str
    chat_id: int | None = None
    source: str = "text"
    mode_hint: str = "auto"
    agent_mode: str = "hybrid"
    mode: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    block_reason: str = ""


@dataclass
class AgentResponse:
    text: str
    mode: str
    iters: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {"text": self.text, "mode": self.mode, "iters": self.iters}
        out.update(self.extra)
        return out
