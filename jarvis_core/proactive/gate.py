"""S4-гейт проактивних дій (TEAM_ECOSYSTEM §7.1, статут S4 human-in-the-loop).

Дефолт — безпека: усе, що мутує стан, виходить назовні, торкається грошей чи
незворотне, потребує підтвердження principal. Авто дозволено лише явно read-only/
draft-діям. Делегатські scopes можуть розширити авто-набір, але НІКОЛИ не знімають
підтвердження з зовнішніх/грошових/незворотних дій (жорсткий інваріант S4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Дії, що завжди read-only/чернеткові — кандидати на авто (якщо scope дозволяє).
_SAFE_KINDS = frozenset({"read", "draft", "summarize", "notify_self", "observe"})
# Жорсткий перелік — ніколи не авто, незалежно від scopes (S4).
_ALWAYS_CONFIRM_KINDS = frozenset({"send", "pay", "delete", "external", "schedule_external"})


@dataclass(frozen=True)
class ProposedAction:
    """Кандидат-дія з циклу reason→propose."""

    kind: str
    summary: str
    mutating: bool = False
    external: bool = False
    money: bool = False
    irreversible: bool = False
    meta: dict[str, object] = field(default_factory=dict)


def requires_confirmation(action: ProposedAction, scopes: frozenset[str] | set[str] = frozenset()) -> bool:
    """True → дію не можна виконувати без явного ✅ principal (S4)."""
    if (
        action.external
        or action.money
        or action.irreversible
        or action.kind in _ALWAYS_CONFIRM_KINDS
    ):
        return True  # жорсткий інваріант — scopes не рятують
    if action.kind in _SAFE_KINDS and not action.mutating:
        return False  # явно безпечна, не мутуюча
    # Мутуюча, але локальна/нечутлива: авто лише за явним scope `act:auto`.
    if action.mutating:
        return "act:auto" not in scopes
    return False


def gate_actions(
    actions: list[ProposedAction], scopes: frozenset[str] | set[str] = frozenset()
) -> tuple[list[ProposedAction], list[ProposedAction]]:
    """Розділяє кандидатів на (auto, needs_confirm) за політикою S4."""
    auto: list[ProposedAction] = []
    confirm: list[ProposedAction] = []
    for a in actions:
        (confirm if requires_confirmation(a, scopes) else auto).append(a)
    return auto, confirm
