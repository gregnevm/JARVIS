"""Проактивний рушій делегата (Стовп D / TEAM_ECOSYSTEM TC-5).

Цикл observe→reason→propose→GATE→act. Цей пакет — чиста доменна частина GATE (S4):
класифікація запропонованих дій на авто-виконувані (read-only/draft) vs ті, що
ЗАВЖДИ потребують підтвердження principal (мутуюче/зовнішнє/гроші/незворотне).
Сам цикл (LLM-reason, диспетч) — у викличному шарі (tools `delegate_tick`).
"""
from __future__ import annotations

from .gate import ProposedAction, gate_actions, requires_confirmation
from .watchers import overdue_steps, process_watch_proposals

__all__ = [
    "ProposedAction",
    "gate_actions",
    "requires_confirmation",
    "overdue_steps",
    "process_watch_proposals",
]
