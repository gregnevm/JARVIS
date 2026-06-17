"""Форматування знайдених паспортів у контекст-блок для промпта агента (consumption).

Чиста функція (InputDecorator-помічник, DESIGN §4.3) — формує рядок із summary
паспортів для інжекту в RAG-контекст. Без HTTP/DB: ретрив робить виклик
(memory `/context/search`), тут лише презентація.
"""
from __future__ import annotations

from typing import Any

_MAX_SUMMARY = 240


def format_context_block(passports: list[dict[str, Any]], max_items: int = 5) -> str:
    """Паспорти → `summary | summary | …` (top max_items, порожні пропущені)."""
    lines: list[str] = []
    for p in passports[:max_items]:
        summary = str(p.get("summary", "")).strip()
        if summary:
            lines.append(summary[:_MAX_SUMMARY])
    return " | ".join(lines)
