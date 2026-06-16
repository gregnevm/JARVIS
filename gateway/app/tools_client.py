"""Клієнт Tools-сервісу: Gateway → POST /agent (DESIGN — агент-луп у Python, без n8n).

R3: god-object (873 рядки) розбито на доменні mixin-и зі спільною базою
(`tools_client_base.ToolsClientBase`). `ToolsClient` лишається тонким агрегатором —
публічний API (усі методи + `extract_text`/`FALLBACK`) незмінний для зворотної сумісності.

- Agent        — tools_client_agent.py        (/agent, /agent/stream)
- Computer Use — tools_client_computer.py      (/computer/*)
- Jobs/Plans   — tools_client_jobs.py          (/tasks, /reminders, /dataset, /bgjobs, /agent/plan*)
- Orchestration— tools_client_orchestrator.py  (research/cursor/mcp/skills/subagents/teams/improve)
"""
from __future__ import annotations

from .tools_client_agent import AgentMixin
from .tools_client_base import FALLBACK, ToolsClientBase, extract_text
from .tools_client_computer import ComputerMixin
from .tools_client_jobs import JobsMixin
from .tools_client_orchestrator import OrchestratorMixin

__all__ = ["FALLBACK", "ToolsClient", "extract_text"]


class ToolsClient(AgentMixin, ComputerMixin, JobsMixin, OrchestratorMixin, ToolsClientBase):
    """Агрегатор усіх доменних mixin-ів. Спільний HTTP-плумбінг — у ToolsClientBase."""
