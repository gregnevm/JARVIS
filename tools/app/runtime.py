"""Runtime-налаштування агента (режим, перевизначення з Telegram)."""
from __future__ import annotations

from .config import settings

_mode_override: str | None = None


def get_agent_mode() -> str:
    return (_mode_override or settings.agent_mode).lower()


def set_agent_mode(mode: str) -> str:
    global _mode_override
    m = mode.lower().strip()
    if m not in ("chat", "agent", "hybrid", "computer"):
        raise ValueError("mode must be chat, agent, hybrid, or computer")
    _mode_override = m
    return m


def clear_agent_mode() -> str:
    global _mode_override
    _mode_override = None
    return settings.agent_mode.lower()
