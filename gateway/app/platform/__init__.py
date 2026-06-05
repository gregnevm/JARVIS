"""JARVIS Platform — self-hosted веб-консоль `/platform`.

Thin UI поверх gateway/tools/memory: Overview, Workbench (SSE), Memory browser,
Logs, Settings, Users, Models. Auth — Telegram admin initData або HTTP Basic
(PLATFORM_PASSWORD / ADMIN_PANEL_PASSWORD). Деталі: docs/PLATFORM_ROADMAP.md.
"""
from __future__ import annotations

from .router import router

__all__ = ["router"]
