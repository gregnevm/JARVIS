"""Org-graph домен (Стовп D / TEAM_ECOSYSTEM TC-0).

Доменні поняття командної екосистеми — squad-ієрархія, типізовані ребра графа
зв'язків, делегати. Framework-нейтральні frozen-dataclasses (без DB/HTTP/FastAPI),
імпортовні будь-де (як `context.py`/`passport`). Зберігання — Postgres/memory,
I/O — gateway/tools; цей пакет — лише домен (P8, статут §5).
"""
from __future__ import annotations

from .models import (
    REL_KINDS,
    SQUAD_KINDS,
    VALID_VISIBILITIES,
    Delegate,
    Relationship,
    Squad,
    SquadMember,
)
from .graph import OrgGraph, interaction_edges
from .visibility import VisibleResource, can_read
from .delegate import DelegateActor, delegate_actor

__all__ = [
    "DelegateActor",
    "delegate_actor",
    "REL_KINDS",
    "SQUAD_KINDS",
    "VALID_VISIBILITIES",
    "Delegate",
    "Relationship",
    "Squad",
    "SquadMember",
    "OrgGraph",
    "interaction_edges",
    "VisibleResource",
    "can_read",
]
