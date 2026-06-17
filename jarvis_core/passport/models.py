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
        }
