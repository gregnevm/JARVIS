"""Team-ecosystem sub-package (Стовп D) — store для org-графа й делегатів.

Тонкий шар персисту над `squads`/`squad_members`/`relationships`/`delegates`
(міграція 004). Домен (граф, видимість) — у `jarvis_core.orggraph`; тут лише I/O.
"""
from __future__ import annotations

from .routes import router

__all__ = ["router"]
