"""Виконавець context-maintenance jobs (tools-сторона інтеграційного шва).

Зв'язує доменні джоби `jarvis_core.passport.jobs` (чисте оркестрування) з реальними
memory (`/context/*`) та Ollama-summarizer. Тригер — ручний (route `/context/jobs/*`),
без auto-cron (ADR-008 philosophy: maintenance із нагляду, не фоном).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from jarvis_core.passport import build_daily, build_proposals, run_retention, summarize_pending
from jarvis_core.passport.jobs import Summarizer

from .config import settings
from .memory_client import MemoryClient

logger = logging.getLogger("jarvis.tools.context_jobs")

CONTEXT_JOB_NAMES = frozenset(
    {"context_summarize", "context_daily", "context_retention", "context_proposal"}
)


class _MemoryContextStore:
    """Адаптер MemoryClient → jarvis_core.passport.ContextStore (Protocol)."""

    def __init__(self, mem: MemoryClient) -> None:
        self._mem = mem

    async def pending(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        return await self._mem.context_pending(user_id, limit)

    async def update(
        self, event_db_id: int, user_id: int, *, summary: str, tags: list[str], kind: str
    ) -> dict[str, Any]:
        return await self._mem.context_update(event_db_id, user_id, summary, tags, kind)

    async def recent(
        self, user_id: int, limit: int, *, kind: str | None = None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return await self._mem.context_recent(user_id, limit, kind, tags)

    async def ingest(self, store: dict[str, Any]) -> dict[str, Any]:
        return await self._mem.context_ingest(store)

    async def purge(
        self, user_id: int, *, before: str | None = None, kind: str | None = None
    ) -> int:
        return await self._mem.context_purge(user_id, before, kind)


def make_summarizer(chat_backend: Any) -> Summarizer:
    """Ollama-summarizer на швидкій chat-моделі (P9 — dense, без води)."""

    async def summarize(text: str) -> str:
        prompt = (
            "Стисни наступний контекст у 1–2 щільні речення українською, без води, "
            "зберігши ключові факти, імена та дати:\n\n" + text
        )
        msg = await chat_backend.chat(
            settings.ollama_model_chat, [{"role": "user", "content": prompt}]
        )
        return str((msg or {}).get("content") or "").strip()

    return summarize


def make_proposer(chat_backend: Any) -> Summarizer:
    """LLM-генератор проактивних пропозицій (S4: лише пропозиція, виконання — з підтвердженням)."""

    async def propose(text: str) -> str:
        prompt = (
            "Ось контекст користувача (нотатки/дзвінки/повідомлення за останній час). "
            "Запропонуй до 3 конкретних КОРИСНИХ дій (по одній на рядок, дієслово на початку, "
            "коротко, українською). Тільки пропозиції, без преамбул:\n\n" + text
        )
        msg = await chat_backend.chat(
            settings.ollama_model_chat, [{"role": "user", "content": prompt}]
        )
        return str((msg or {}).get("content") or "").strip()

    return propose


async def run_context_job(
    name: str,
    memory: MemoryClient,
    chat_backend: Any,
    user_id: int,
    *,
    day: str,
    now: datetime,
) -> dict[str, Any]:
    """Запускає одну context-maintenance job. Кидає ValueError для невідомої назви."""
    store = _MemoryContextStore(memory)
    if name == "context_summarize":
        n = await summarize_pending(store, make_summarizer(chat_backend), user_id)
        return {"job": name, "summarized": n}
    if name == "context_daily":
        res = await build_daily(store, make_summarizer(chat_backend), user_id, day=day)
        if res is not None:
            from . import push

            await push.publish("Щоденний контекст оновлено", title="JARVIS")
        return {"job": name, "created": res is not None, "result": res}
    if name == "context_retention":
        out = await run_retention(store, user_id, now=now)
        return {"job": name, "purged": out, "total": sum(out.values())}
    if name == "context_proposal":
        proposals = await build_proposals(store, make_proposer(chat_backend), user_id)
        if proposals:
            from . import push

            await push.publish("Пропозиції: " + "; ".join(proposals), title="JARVIS")
        return {"job": name, "proposals": proposals, "count": len(proposals)}
    raise ValueError(f"unknown context job: {name}")
