"""Process engine домен (Стовп D / TEAM_ECOSYSTEM TC-6).

Довгоживучі cross-actor бізнес-процеси по ієрархії команди — машина станів
(паттерн State + Mediator) над наявним async + bg_jobs (НЕ Celery/Temporal, статут §6).
Чистий домен: рахує готові кроки й переходи; диспетч (bg job / нагадування / HITL)
робить викличний шар (tools/gateway).
"""
from __future__ import annotations

from .models import (
    STEP_KINDS,
    STEP_STATUSES,
    PROCESS_STATUSES,
    Process,
    ProcessStep,
)
from .engine import advance, escalation_target, is_complete, ready_steps

__all__ = [
    "STEP_KINDS",
    "STEP_STATUSES",
    "PROCESS_STATUSES",
    "Process",
    "ProcessStep",
    "advance",
    "escalation_target",
    "is_complete",
    "ready_steps",
]
