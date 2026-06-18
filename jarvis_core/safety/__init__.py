"""Safety-примітиви для автономних агент-лупів (kaizen safety_guard-порт).

Framework-нейтральні, чисті — імпортовні будь-де (включно з офлайн Edge).
"""
from __future__ import annotations

from jarvis_core.safety.blast_radius import BlastRadius, path_allowed

__all__ = ["BlastRadius", "path_allowed"]
