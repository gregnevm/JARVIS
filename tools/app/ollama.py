"""Backward-compat exports."""
from __future__ import annotations

from jarvis_core.llm.chat import OllamaChatBackend
from jarvis_core.llm.exceptions import CircuitOpen

OllamaClient = OllamaChatBackend

__all__ = ["OllamaClient", "CircuitOpen"]
