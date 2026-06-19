"""Машина станів процесу (TEAM_ECOSYSTEM §6.2).

Чисті функції над `Process`: які кроки готові (залежності виконані), застосувати
перехід кроку, чи процес завершено, куди ескалувати approval по `reports_to`.
Жодного I/O — диспетч (bg job / reminder / HITL) робить tools/gateway.
"""
from __future__ import annotations

from .models import Process, ProcessStep

# Кроки, що вважаються «закритими» для розрахунку залежностей.
_TERMINAL = frozenset({"done", "skipped"})


def ready_steps(proc: Process) -> list[ProcessStep]:
    """Кроки в `pending`, усі залежності яких уже в done/skipped — готові до запуску."""
    done_ids = {s.id for s in proc.steps if s.status in _TERMINAL}
    out: list[ProcessStep] = []
    for s in proc.steps:
        if s.status != "pending":
            continue
        if all(dep in done_ids for dep in s.depends_on):
            out.append(s)
    return out


def advance(proc: Process, step_id: str, status: str) -> bool:
    """Застосовує перехід кроку. Повертає True, якщо змінено.

    Невідомий крок / невалідний статус → False (нічого не міняємо). Після
    переходу синхронізує статус процесу (running/done) через `_sync_status`.
    """
    from .models import STEP_STATUSES

    if status not in STEP_STATUSES:
        return False
    target = next((s for s in proc.steps if s.id == step_id), None)
    if target is None or target.status == status:
        return False
    target.status = status
    _sync_status(proc)
    return True


def _sync_status(proc: Process) -> None:
    # cancelled/paused — липкі (не воскресають переходом кроку).
    if proc.status in ("cancelled", "paused"):
        return
    # Незайманий draft (жоден крок ще не зрушив) лишається draft.
    if proc.status == "draft" and not any(s.status != "pending" for s in proc.steps):
        return
    # Інакше — єдине рішення done/running. Раніше draft робив ранній `return` ПІСЛЯ
    # bump-у в "running", тож draft, який завершується ОДНИМ переходом (процес із
    # одного кроку, або останній pending-крок прямо з draft), залипав у "running"
    # назавжди й ніколи не ставав "done".
    proc.status = "done" if is_complete(proc) else "running"


def is_complete(proc: Process) -> bool:
    """Усі кроки термінальні (done/skipped) і їх щонайменше один."""
    return bool(proc.steps) and all(s.status in _TERMINAL for s in proc.steps)


def escalation_target(
    proc: Process, step: ProcessStep, manager_chain: list[str]
) -> str | None:
    """Куди ескалувати простроченого approval/human-крок — перший керівник у ланцюгу.

    `manager_chain` — від прямого менеджера вгору (як `OrgGraph.manager_chain`).
    None, якщо керівників немає (вершина ієрархії)."""
    return manager_chain[0] if manager_chain else None
