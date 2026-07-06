"""Збирання ФІНІШНОГО паспорта перед ingest (R3 «Тонкий шлюз», S3).

Дві швидкості (CONTEXT_MODULE §2):
  * fast — є `summary` → серверна редакція і в store;
  * raw  — лише `content` → провізорний summary з excerpt, raw у payload,
           тег `pending:summary` (bg_job `summarize_pending` дозведе і зніме тег).

Раніше жило в `gateway/app/client_api/context.py` (`_build_store`) — тепер домен
у ядрі, gateway-хендлер лише мапить свою pydantic-модель на цей виклик (I/O).
"""
from __future__ import annotations

from typing import Any

from .jobs import PENDING_SUMMARY_TAG
from .models import Passport, normalize_sensitivity
from .redaction import Redactor
from .tags import normalize_tags

# Довжина провізорного summary з excerpt-у content (raw-швидкість).
PROVISIONAL_SUMMARY_LEN = 240


def build_store_event(
    *,
    user_id: int,
    org_id: str,
    redactor: Redactor,
    kind: str | None = None,
    summary: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    sensitivity: str | None = None,
    source: str | None = None,
    ref: str | None = None,
    event_id: str | None = None,
    event_ts: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Будує фінішний store-паспорт (редакція + нормалізація тегів + org/user).

    Порожня подія (ні summary, ні content) → `store["summary"] == ""` —
    виклик рахує її як failed (контракт ingest незмінний).
    """
    kind_n = (kind or "note").strip() or "note"
    payload_n = dict(payload or {})
    tags_n = list(tags or [])
    raw_summary = (summary or "").strip()
    if raw_summary:
        summary_n = raw_summary
    else:
        content_n = (content or "").strip()
        summary_n = content_n[:PROVISIONAL_SUMMARY_LEN]
        if content_n:
            payload_n.setdefault("raw", content_n)
            tags_n.append(PENDING_SUMMARY_TAG)
    passport = Passport(
        kind=kind_n,
        summary=summary_n,
        tags=normalize_tags(tags_n, kind_n),
        sensitivity=normalize_sensitivity(sensitivity),
        source=source,
        ref=ref,
        event_id=event_id,
        event_ts=event_ts,
        payload=payload_n,
    )
    # Серверна (друга) редакція: вирізає секрети/PII, прибирає raw для health/finance.
    passport = redactor.redact_passport(passport)
    store = passport.to_store()
    store["user_id"] = user_id
    store["org_id"] = org_id
    return store
