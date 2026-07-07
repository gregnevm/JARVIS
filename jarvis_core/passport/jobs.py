"""Context maintenance jobs (scheduled sweeps) — НЕ interactive `JOB_TYPES`.

Окремо від user-facing черги (`jarvis_core.bg_jobs`): це обслуговуючі прогони
(прецедент розділення — ADR-008 manual-scan). Чисте оркестрування над
`ContextStore` (Protocol) + `Summarizer` (callable) — unit-тестовно з фейками,
без мережі/БД/Ollama (S3, test-first). Виконавець із реальними memory+Ollama —
у tools (інтеграційний шов; тригер manual або scheduler).

  context_summarize — дозводить `pending:summary` паспорти через LLM.
  context_daily     — зводить паспорти дня в один `kind:daily` паспорт.
  context_retention — чистить прострочені паспорти за per-kind TTL.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from .tags import normalize_tags, split_tag

Summarizer = Callable[[str], Awaitable[str]]

# Зрізає РІВНО один провідний маркер списку (bullet або нумерацію), а не набір символів.
# `str.lstrip(charset)` жер БУДЬ-ЯКІ провідні символи з набору — тобто корупив контент,
# що легітимно починається з цифри/крапки ("3D print" -> "D print", "911 call" -> "call").
# Роздільник `(?:\s+|$)` після маркера обов'язковий, тому:
#   • "-5 degrees" / "1.Book" (маркер, зліплений із текстом) лишаються ЦІЛИМИ;
#   • справжні LLM-списки ("1. text", "- text", "• text") нормалізуються;
#   • рядок-лише-маркер ("-", "1.", "• ") згортається в "" → пропускається в build_proposals
#     (без цього старий lstrip-контракт ламався: сирий "-" протікав як junk-пропозиція).
_MARKER_RE = re.compile(r"^(?:[-+•*–—]|\d{1,3}[.)])(?:\s+|$)")


def _strip_marker(line: str) -> str:
    """Прибирає провідний enumeration-маркер (одну штуку); рядок-лише-маркер → ""."""
    return _MARKER_RE.sub("", line.strip(), count=1).strip()


PENDING_SUMMARY_TAG = "pending:summary"
DISTILLED_KIND = "distilled"
LEARNED_STATUS_TAG = "status:learned"
CONTEXT_JOB_NAMES = frozenset(
    {
        "context_summarize",
        "context_daily",
        "context_retention",
        "context_proposal",
        "context_distill",
    }
)

# Per-kind retention (дні). raw-сигнали — коротко; нотатки/daily/distilled — довго.
# distilled = найдовговічніший рівень (T3, дистильоване знання) → як daily.
DEFAULT_RETENTION_DAYS: dict[str, int] = {
    "notification": 14,
    "sms": 30,
    "call": 30,
    "usage": 7,
    "note": 365,
    "daily": 3650,
    "distilled": 3650,
}


class ContextStore(Protocol):
    """Порт до memory `/context/*` (реалізація-адаптер — у tools)."""

    async def pending(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...
    async def update(
        self, event_db_id: int, user_id: int, *, summary: str, tags: list[str], kind: str
    ) -> dict[str, Any]: ...
    async def recent(
        self, user_id: int, limit: int, *, kind: str | None = None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]: ...
    async def ingest(self, store: dict[str, Any]) -> dict[str, Any]: ...
    async def purge(
        self, user_id: int, *, before: str | None = None, kind: str | None = None
    ) -> int: ...


def _kind_of(tags: list[str]) -> str:
    for t in tags:
        ns, val = split_tag(t)
        if ns == "kind":
            return val or "note"
    return "note"


def _has_kind(tags: list[str], kind: str) -> bool:
    return f"kind:{kind}" in tags


async def summarize_pending(
    store: ContextStore, summarizer: Summarizer, user_id: int, *, limit: int = 20
) -> int:
    """Дозводить raw-паспорти (тег pending:summary) у якісний summary, знімає тег. К-сть оброблених."""
    items = await store.pending(user_id, limit)
    done = 0
    for it in items:
        payload = it.get("payload") or {}
        raw = str(payload.get("raw") or it.get("summary") or "").strip()
        if not raw:
            continue
        summary = (await summarizer(raw)).strip()
        if not summary:
            continue
        tags = it.get("tags") or []
        kind = _kind_of(tags)
        new_tags = [t for t in tags if t != PENDING_SUMMARY_TAG]
        await store.update(int(it["id"]), user_id, summary=summary, tags=new_tags, kind=kind)
        done += 1
    return done


async def build_daily(
    store: ContextStore, summarizer: Summarizer, user_id: int, *, day: str, limit: int = 200
) -> dict[str, Any] | None:
    """Зводить недавні паспорти в один `kind:daily`. Ідемпотентно по event_id=daily:{uid}:{day}."""
    items = await store.recent(user_id, limit)
    src = [it for it in items if not _has_kind(it.get("tags") or [], "daily")]
    joined = "\n".join(f"- {it.get('summary', '')}" for it in src if it.get("summary"))
    if not joined.strip():
        return None
    summary = (await summarizer(joined)).strip()
    if not summary:
        return None
    store_dict: dict[str, Any] = {
        "user_id": user_id,
        "kind": "daily",
        "summary": summary,
        "tags": normalize_tags([f"day:{day}"], "daily"),
        "source": "context_daily",
        "event_id": f"daily:{user_id}:{day}",
    }
    return await store.ingest(store_dict)


async def build_proposals(
    store: ContextStore,
    proposer: Summarizer,
    user_id: int,
    *,
    recent_limit: int = 30,
    max_n: int = 3,
) -> list[str]:
    """Генерує проактивні пропозиції дій із недавнього контексту → паспорти `kind:proposal`.

    Пропозиція — звичайний паспорт (переюз інфри, YAGNI): `summary` = дія, тег `status:offered`.
    `proposer` повертає пропозиції рядками (по одній на рядок). Повертає список тексту пропозицій."""
    items = await store.recent(user_id, recent_limit)
    src = [
        it
        for it in items
        if not _has_kind(it.get("tags") or [], "proposal")
        and not _has_kind(it.get("tags") or [], "daily")
    ]
    ctx = "\n".join(f"- {it.get('summary', '')}" for it in src if it.get("summary"))
    if not ctx.strip():
        return []
    raw = await proposer(ctx)
    proposals: list[str] = []
    for line in raw.splitlines():
        text = _strip_marker(line)
        if text:
            proposals.append(text)
        if len(proposals) >= max_n:
            break
    for p in proposals:
        await store.ingest(
            {
                "user_id": user_id,
                "kind": "proposal",
                "summary": p,
                "tags": normalize_tags(["status:offered"], "proposal"),
                "source": "context_proposal",
            }
        )
    return proposals


async def build_distilled(
    store: ContextStore,
    distiller: Summarizer,
    user_id: int,
    *,
    recent_limit: int = 50,
    max_n: int = 5,
) -> list[str]:
    """Дистилює недавні паспорти у стабільні салієнтні факти → `kind:distilled` (T3).

    Рівень T3 памʼяті (AO-CTX §2, Mem0-паттерн salience): не сирі події, а
    витягнуті довговічні факти про оператора/бізнес. Дзеркалить `build_proposals`
    (реюз інфри, YAGNI): факт — звичайний паспорт із `status:learned`.

    **Provenance FAIL-CLOSED (C1):** без source-id жоден факт не пишеться —
    `source_passport_ids` у payload обовʼязковий (інакше «голий» дистилят =
    неперевірюване знання). Виключає власні (distilled/daily/proposal) паспорти
    з входу, щоб не дистилювати дистилят (feedback loop)."""
    items = await store.recent(user_id, recent_limit)
    src = [
        it
        for it in items
        if not _has_kind(it.get("tags") or [], DISTILLED_KIND)
        and not _has_kind(it.get("tags") or [], "daily")
        and not _has_kind(it.get("tags") or [], "proposal")
    ]
    source_ids = [
        str(it.get("id") if it.get("id") is not None else it.get("event_id"))
        for it in src
        if it.get("id") is not None or it.get("event_id")
    ]
    ctx = "\n".join(f"- {it.get('summary', '')}" for it in src if it.get("summary"))
    if not ctx.strip() or not source_ids:  # provenance fail-closed
        return []
    raw = await distiller(ctx)
    facts: list[str] = []
    for line in raw.splitlines():
        text = _strip_marker(line)
        if text:
            facts.append(text)
        if len(facts) >= max_n:
            break
    for fact in facts:
        await store.ingest(
            {
                "user_id": user_id,
                "kind": DISTILLED_KIND,
                "summary": fact,
                "tags": normalize_tags([LEARNED_STATUS_TAG], DISTILLED_KIND),
                "source": "context_distill",
                "payload": {"source_passport_ids": source_ids},
            }
        )
    return facts


async def run_retention(
    store: ContextStore,
    user_id: int,
    *,
    now: datetime,
    policy: dict[str, int] | None = None,
) -> dict[str, int]:
    """Чистить прострочені паспорти per-kind (cutoff = now - TTL). Повертає {kind: deleted}."""
    pol = policy or DEFAULT_RETENTION_DAYS
    out: dict[str, int] = {}
    for kind, days in pol.items():
        before = (now - timedelta(days=days)).isoformat()
        out[kind] = await store.purge(user_id, before=before, kind=kind)
    return out
