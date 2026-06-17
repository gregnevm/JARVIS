"""Watchers (Стовп D / TEAM_ECOSYSTEM TC-5, §7.2).

Чисті детектори сигналів, що потребують уваги делегата: прострочені кроки процесів,
заблоковані кроки. Повертають read-only `notify`-пропозиції (S4: лише сповіщення —
нічого не виконують). Споживач — проактивний цикл `delegate_tick`.
"""
from __future__ import annotations

from ..process.models import Process
from .gate import ProposedAction

_TERMINAL = frozenset({"done", "skipped"})


def overdue_steps(proc: Process, now_iso: str) -> list[str]:
    """ID кроків із `due` < now і не-термінальним статусом (прострочені SLA)."""
    out: list[str] = []
    for s in proc.steps:
        if s.status in _TERMINAL or not s.due:
            continue
        if str(s.due) < now_iso:  # ISO-8601 лексикографічно впорядкований
            out.append(s.id)
    return out


def process_watch_proposals(processes: list[Process], now_iso: str) -> list[ProposedAction]:
    """Read-only пропозиції-сповіщення про прострочені кроки активних процесів."""
    out: list[ProposedAction] = []
    for proc in processes:
        if proc.status not in ("running", "draft"):
            continue
        for step_id in overdue_steps(proc, now_iso):
            step = next((s for s in proc.steps if s.id == step_id), None)
            if step is None:
                continue
            out.append(
                ProposedAction(
                    kind="notify",
                    summary=f"Прострочено крок «{step.title}» процесу «{proc.title}»",
                    meta={"process_id": proc.id, "step_id": step_id, "assignee": step.assignee_user_id},
                )
            )
    return out
