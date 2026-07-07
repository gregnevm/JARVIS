"""Context maintenance jobs (summarize/daily/retention) — оркестрування з фейками."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from jarvis_core.passport import (
    build_daily,
    build_distilled,
    build_proposals,
    run_retention,
    summarize_pending,
)


class FakeStore:
    """In-memory фейк ContextStore — фіксує виклики, без мережі/БД."""

    def __init__(self, pending: list[dict] | None = None, recent: list[dict] | None = None) -> None:
        self._pending = pending or []
        self._recent = recent or []
        self.updated: list[dict[str, Any]] = []
        self.ingested: list[dict[str, Any]] = []
        self.purged: list[dict[str, Any]] = []

    async def pending(self, user_id: int, limit: int) -> list[dict]:
        return self._pending[:limit]

    async def update(self, event_db_id, user_id, *, summary, tags, kind) -> dict:
        self.updated.append({"id": event_db_id, "summary": summary, "tags": tags, "kind": kind})
        return {"ok": True}

    async def recent(self, user_id, limit, *, kind=None, tags=None) -> list[dict]:
        return self._recent[:limit]

    async def ingest(self, store: dict) -> dict:
        self.ingested.append(store)
        return {"id": 1, "inserted": True}

    async def purge(self, user_id, *, before=None, kind=None) -> int:
        self.purged.append({"before": before, "kind": kind})
        return 1


async def _summarizer(text: str) -> str:
    return f"SUMMARY({len(text)})"


# --- context_summarize ---

async def test_summarize_pending_upgrades_and_drops_tag():
    store = FakeStore(pending=[
        {"id": 7, "summary": "excerpt", "tags": ["kind:worklog", "pending:summary"],
         "payload": {"raw": "довгий сирий текст"}},
    ])
    n = await summarize_pending(store, _summarizer, user_id=42)
    assert n == 1
    upd = store.updated[0]
    assert upd["id"] == 7
    assert upd["summary"].startswith("SUMMARY")
    assert "pending:summary" not in upd["tags"]   # тег знято
    assert upd["kind"] == "worklog"               # kind збережено з тегів


async def test_summarize_pending_skips_empty_raw():
    store = FakeStore(pending=[{"id": 1, "summary": "", "tags": ["pending:summary"], "payload": {}}])
    assert await summarize_pending(store, _summarizer, user_id=1) == 0
    assert store.updated == []


# --- context_daily ---

async def test_build_daily_aggregates_into_one_passport():
    store = FakeStore(recent=[
        {"summary": "купив молоко", "tags": ["kind:note"]},
        {"summary": "дзвінок мамі", "tags": ["kind:call"]},
    ])
    res = await build_daily(store, _summarizer, 42, day="2026-06-16")
    assert res is not None
    daily = store.ingested[0]
    assert daily["kind"] == "daily"
    assert daily["event_id"] == "daily:42:2026-06-16"   # ідемпотентність
    assert "kind:daily" in daily["tags"] and "day:2026-06-16" in daily["tags"]


async def test_build_daily_excludes_prior_daily_and_noop_when_empty():
    store = FakeStore(recent=[{"summary": "вчора", "tags": ["kind:daily"]}])
    assert await build_daily(store, _summarizer, 1, day="2026-06-16") is None
    assert store.ingested == []


# --- context_proposal ---

async def _proposer(text: str) -> str:
    return "1. Передзвонити мамі\n- Оплатити рахунок\n• Відповісти Орестові"


async def test_build_proposals_ingests_kind_proposal():
    store = FakeStore(recent=[{"summary": "мама дзвонила", "tags": ["kind:call"]}])
    out = await build_proposals(store, _proposer, 42, max_n=3)
    assert out == ["Передзвонити мамі", "Оплатити рахунок", "Відповісти Орестові"]  # маркери зрізано
    assert len(store.ingested) == 3
    assert store.ingested[0]["kind"] == "proposal"
    assert "status:offered" in store.ingested[0]["tags"]


async def test_build_proposals_noop_when_only_proposals_or_daily():
    store = FakeStore(recent=[{"summary": "стара", "tags": ["kind:proposal"]}])
    assert await build_proposals(store, _proposer, 1) == []
    assert store.ingested == []


async def _digit_proposer(text: str) -> str:
    # Контент, що ЛЕГІТИМНО починається з цифри/маркер-символу — не має корупитися.
    return "3D print a mount\n2024 tax review\n911 call plumber"


async def test_build_proposals_preserves_leading_digit_content():
    # Регресія на баг lstrip(charset): "3D..."-> "D...", "911..."-> "call..." (втрата даних).
    store = FakeStore(recent=[{"summary": "щось", "tags": ["kind:note"]}])
    out = await build_proposals(store, _digit_proposer, 7, max_n=3)
    assert out == ["3D print a mount", "2024 tax review", "911 call plumber"]
    assert [g["summary"] for g in store.ingested] == out  # персист теж не зіпсовано


async def _mixed_marker_proposer(text: str) -> str:
    return "1. Book flight\n12. Renew\n3) Pay bill\n- Call mom\n• Reply\n* Todo\n+ Plus item"


async def test_build_proposals_strips_only_marker():
    store = FakeStore(recent=[{"summary": "щось", "tags": ["kind:note"]}])
    out = await build_proposals(store, _mixed_marker_proposer, 3, max_n=7)
    assert out == ["Book flight", "Renew", "Pay bill", "Call mom", "Reply", "Todo", "Plus item"]


async def _junk_bullet_proposer(text: str) -> str:
    # Реалістичний LLM-вивід із порожнім/висячим маркером — не має протікати як пропозиція
    # і не має з'їдати max_n-бюджет (регресія проти старого lstrip, який згортав "-" у "").
    # Покриваємо ВСІ форми маркера (-, *, •, N)), не лише дефіс.
    return "- Book flight\n- Call mom\n-\n- \n*\n•\n1)"


async def test_build_proposals_drops_marker_only_lines():
    store = FakeStore(recent=[{"summary": "щось", "tags": ["kind:note"]}])
    out = await build_proposals(store, _junk_bullet_proposer, 5, max_n=3)
    assert out == ["Book flight", "Call mom"]           # жодного junk "-"
    assert [g["summary"] for g in store.ingested] == out  # і в сторі теж чисто


async def _overflow_proposer(text: str) -> str:
    # 5 валідних рядків проти max_n=3 — пін на break-трункацію
    # і на те, що персист іде по ТРУНКОВАНОМУ списку, а не по всіх рядках.
    return "1. A\n2. B\n3. C\n4. D\n5. E"


async def test_build_proposals_truncates_to_max_n_and_persists_only_kept():
    store = FakeStore(recent=[{"summary": "щось", "tags": ["kind:note"]}])
    out = await build_proposals(store, _overflow_proposer, 9, max_n=3)
    assert out == ["A", "B", "C"]                        # D/E відкинуто
    assert [g["summary"] for g in store.ingested] == out  # у стор пішли лише збережені 3


def test_strip_marker_edge_cases():
    from jarvis_core.passport.jobs import _strip_marker

    assert _strip_marker("1. Book flight") == "Book flight"
    assert _strip_marker("12) Renew") == "Renew"
    assert _strip_marker("  - Call mom  ") == "Call mom"
    assert _strip_marker("– Call mom") == "Call mom"     # en-dash bullet
    assert _strip_marker("— Reply") == "Reply"           # em-dash bullet
    assert _strip_marker("+ Plus item") == "Plus item"   # markdown "+" bullet
    assert _strip_marker("+5 degrees") == "+5 degrees"   # зліплений плюс цілий
    assert _strip_marker("999. task") == "task"          # 3-цифровий маркер зрізано
    assert _strip_marker("3D print a mount") == "3D print a mount"  # цифра-контент цілий
    assert _strip_marker("1234. deep dive") == "1234. deep dive"    # 4-цифровий → не маркер
    assert _strip_marker("-5 degrees") == "-5 degrees"   # зліплений дефіс цілий
    assert _strip_marker("1.Book") == "1.Book"           # маркер, зліплений із текстом — цілий
    assert _strip_marker("-") == ""                       # рядок-лише-маркер → ""
    assert _strip_marker("1. ") == ""                     # маркер + хвостовий пробіл → ""
    assert _strip_marker("") == ""
    assert _strip_marker("   ") == ""


# --- context_distill (T3 memory tier, AO-CTX Ф1) ---

async def _distiller(text: str) -> str:
    return "Оператор працює з дрон-поставками\nПлатить через IBAN, не готівкою"


async def test_build_distilled_ingests_kind_distilled_with_provenance():
    store = FakeStore(recent=[
        {"id": 11, "summary": "рахунок від постачальника FPV", "tags": ["kind:note"]},
        {"id": 12, "summary": "оплата по IBAN", "tags": ["kind:note"]},
    ])
    out = await build_distilled(store, _distiller, 42, max_n=5)
    assert out == ["Оператор працює з дрон-поставками", "Платить через IBAN, не готівкою"]
    assert len(store.ingested) == 2
    rec = store.ingested[0]
    assert rec["kind"] == "distilled"
    assert "status:learned" in rec["tags"] and "kind:distilled" in rec["tags"]
    # provenance — обовʼязковий (fail-closed C1)
    assert rec["payload"]["source_passport_ids"] == ["11", "12"]


async def test_build_distilled_fail_closed_without_source_ids():
    # Паспорти без id/event_id → provenance неможлива → нічого не пишемо.
    store = FakeStore(recent=[{"summary": "факт без id", "tags": ["kind:note"]}])
    assert await build_distilled(store, _distiller, 1) == []
    assert store.ingested == []


async def test_build_distilled_excludes_own_kinds_no_feedback_loop():
    # distilled/daily/proposal не йдуть на вхід дистиляції (інакше рекурсивний дрейф).
    store = FakeStore(recent=[
        {"id": 1, "summary": "старий дистилят", "tags": ["kind:distilled"]},
        {"id": 2, "summary": "денний звіт", "tags": ["kind:daily"]},
        {"id": 3, "summary": "пропозиція", "tags": ["kind:proposal"]},
    ])
    assert await build_distilled(store, _distiller, 1) == []
    assert store.ingested == []


async def test_build_distilled_uses_event_id_when_no_numeric_id():
    store = FakeStore(recent=[
        {"event_id": "sig:abc", "summary": "подія з event_id", "tags": ["kind:sms"]},
    ])
    out = await build_distilled(store, _distiller, 7, max_n=1)
    assert len(out) == 1
    assert store.ingested[0]["payload"]["source_passport_ids"] == ["sig:abc"]


async def test_build_distilled_respects_max_n():
    async def _many(text: str) -> str:
        return "\n".join(f"факт {i}" for i in range(10))

    store = FakeStore(recent=[{"id": 5, "summary": "щось", "tags": ["kind:note"]}])
    out = await build_distilled(store, _many, 1, max_n=3)
    assert out == ["факт 0", "факт 1", "факт 2"]
    assert len(store.ingested) == 3


async def test_distilled_retention_is_long_lived():
    from jarvis_core.passport import DEFAULT_RETENTION_DAYS

    assert DEFAULT_RETENTION_DAYS["distilled"] == 3650


# --- context_retention ---

async def test_run_retention_purges_each_kind_with_cutoff():
    store = FakeStore()
    now = datetime(2026, 6, 16, 12, 0, 0)
    out = await run_retention(store, 42, now=now, policy={"sms": 30, "usage": 7})
    assert out == {"sms": 1, "usage": 1}
    kinds = {p["kind"] for p in store.purged}
    assert kinds == {"sms", "usage"}
    # cutoff = now - TTL (usage 7д → 2026-06-09)
    usage = next(p for p in store.purged if p["kind"] == "usage")
    assert usage["before"].startswith("2026-06-09")
