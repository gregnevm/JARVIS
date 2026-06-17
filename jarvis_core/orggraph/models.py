"""Доменні моделі org-графа (TEAM_ECOSYSTEM §2, §3.1).

Frozen dataclasses, що дзеркалять таблиці `squads`/`squad_members`/`relationships`/
`delegates` (міграція 004), але без жодної залежності на БД. Канонічні набори
типів — валідація на межах, не магічні рядки (як `context.VALID_ROLES`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Типи ребер графа зв'язків (directed). `delegate_of` зв'язує делегата з principal.
REL_KINDS = frozenset(
    {"reports_to", "manages", "assists", "delegate_of", "collaborates_with"}
)
# Природа squad-вузла.
SQUAD_KINDS = frozenset({"team", "department", "project"})
# Рівні видимості ресурсу (паспорта). Owner-scoped `private` лишається дефолтом.
VALID_VISIBILITIES = frozenset({"private", "squad", "org", "custom"})
DEFAULT_VISIBILITY = "private"

# Джерело ребра: введене людиною vs виведене спостереженням взаємодій (§3.3).
REL_SOURCES = frozenset({"declared", "observed"})


def normalize_visibility(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in VALID_VISIBILITIES else DEFAULT_VISIBILITY


@dataclass(frozen=True)
class Squad:
    """Піддерево організації — відділ / проєктна група."""

    id: str
    org_id: str
    name: str
    parent_id: str | None = None
    kind: str = "team"


@dataclass(frozen=True)
class SquadMember:
    """Членство людини в squad + посада."""

    squad_id: str
    user_id: str
    title: str | None = None
    seniority: str | None = None


@dataclass(frozen=True)
class Relationship:
    """Типізоване ребро графа між двома людьми (org-scoped)."""

    org_id: str
    src_user_id: str
    dst_user_id: str
    kind: str
    weight: float = 1.0
    source: str = "declared"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Delegate:
    """AI-асистент особи — персона + делеговані повноваження (scopes)."""

    id: str
    org_id: str
    principal_id: str
    persona: dict[str, Any] = field(default_factory=dict)
    scopes: tuple[str, ...] = ("read:self",)
    proactive: bool = False
