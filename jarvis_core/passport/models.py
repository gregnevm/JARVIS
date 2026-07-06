"""Passport — носій культури P9 (summarize-all) + P10 (tag-everything).

Канонічна доменна форма паспорта контексту (SSOT, DESIGN §1.2.1). Framework-нейтральна
(без FastAPI/DB/HTTP) — імпортовна будь-де, включно з офлайн Edge (як `context.py`).
Зберігання — `memory/app/context`; I/O — `gateway`; цей модуль — лише домен.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Рівні чутливості (керують глибиною редакції, retention і чи зберігати raw).
VALID_SENSITIVITIES = frozenset({"public", "personal", "health", "finance"})
DEFAULT_SENSITIVITY = "personal"
# Для цих рівнів сире наповнення (payload) НЕ зберігається — лише derived summary.
RAW_FORBIDDEN_SENSITIVITIES = frozenset({"health", "finance"})

DEFAULT_KIND = "note"


def normalize_sensitivity(value: str | None) -> str:
    s = (value or "").strip().lower()
    return s if s in VALID_SENSITIVITIES else DEFAULT_SENSITIVITY


def should_store_raw(sensitivity: str) -> bool:
    """health/finance → False: тримаємо лише summary, сире не персистимо (приватність)."""
    return normalize_sensitivity(sensitivity) not in RAW_FORBIDDEN_SENSITIVITIES


@dataclass(frozen=True)
class Passport:
    """Один значущий артефакт контексту з паспортом (P9/P10).

    `tags` мають містити `kind:<kind>` (інваріант C1) — гарантує `tags.normalize_tags`.
    `payload` для health/finance має бути порожнім (див. `should_store_raw`).
    """

    kind: str
    summary: str
    tags: list[str] = field(default_factory=list)
    sensitivity: str = DEFAULT_SENSITIVITY
    source: str | None = None
    ref: str | None = None
    event_id: str | None = None
    event_ts: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    # Стовп D (TEAM_ECOSYSTEM §4.1) — командна видимість. Дефолти зберігають
    # owner-scoped поведінку (private, без суб'єктів) → solo-user незмінний (S2).
    subjects: list[str] = field(default_factory=list)   # про кого (user_id/tg_id/person:tag)
    visibility: str = "private"                          # private|squad|org|custom
    audience: list[str] = field(default_factory=list)   # явні user_id/squad_id (для custom)
    group_ref: int | None = None                        # chat_id, якщо паспорт із групи

    def to_store(self) -> dict[str, Any]:
        """Плоский dict для memory `/context/ingest` (без owner/org — їх дає RequestContext)."""
        return {
            "kind": self.kind,
            "summary": self.summary,
            "tags": self.tags,
            "sensitivity": self.sensitivity,
            "source": self.source,
            "ref": self.ref,
            "event_id": self.event_id,
            "event_ts": self.event_ts,
            "payload": self.payload,
            "subjects": self.subjects,
            "visibility": self.visibility,
            "audience": self.audience,
            "group_ref": self.group_ref,
        }

    @classmethod
    def from_store(cls, store: dict[str, Any]) -> "Passport":
        """Зворотний до `to_store`: відновлює доменний конверт зі store-dict.

        Owner/org-ключі (`user_id`/`org_id`) ігноруються — вони поза конвертом
        (для шини їх несе `BusMeta`). Використання: emit ПІСЛЯ store (SY-B1)."""
        return cls(
            kind=str(store.get("kind") or DEFAULT_KIND),
            summary=str(store.get("summary") or ""),
            tags=list(store.get("tags") or []),
            sensitivity=normalize_sensitivity(store.get("sensitivity")),
            source=store.get("source"),
            ref=store.get("ref"),
            event_id=store.get("event_id"),
            event_ts=store.get("event_ts"),
            payload=dict(store.get("payload") or {}),
            subjects=list(store.get("subjects") or []),
            visibility=str(store.get("visibility") or "private"),
            audience=list(store.get("audience") or []),
            group_ref=store.get("group_ref"),
        )
