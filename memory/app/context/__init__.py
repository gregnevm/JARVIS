"""Context Passport sub-package (P9/P10/C1) — store+retrieve поверх `context_events`.

Тонкий шар: персист + embed; домен — у `jarvis_core.passport`. Деталі: docs/CONTEXT_MODULE.md.
"""
from __future__ import annotations

from .routes import router

__all__ = ["router"]
