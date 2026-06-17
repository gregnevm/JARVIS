"""Узагальнений агент-engine (R1): tool-loop, спільний для sync/stream/fix.

Транспортно-нейтральний і залежно-легкий: усе сервіс-специфічне (dispatch,
hooks, confirm, статус-мітки) інжектується викликами. Деталі — `tool_loop.py`.
"""
from __future__ import annotations

from jarvis_core.agent.tool_loop import (
    ToolCall,
    ToolStepResult,
    assistant_message,
    extract_tool_calls,
    run_tool_loop,
)

__all__ = [
    "ToolCall",
    "ToolStepResult",
    "assistant_message",
    "extract_tool_calls",
    "run_tool_loop",
]
