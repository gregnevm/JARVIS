"""Usage-метрика LLM → паспорти `kind:usage` (SY-6 «лічильник як декоратор»).

Один потік метрики — три споживачі: `/v1/usage` (білінг AP-треку), self-score
O3 ECO у kaizen, cost-дашборд /platform. SSOT — `context_events`: розбіжність
цифр між споживачами структурно неможлива (D1).

`UsageMeter` акумулює події (model, tokens in/out, latency) і флашить у sink
ОДНИМ агрегат-паспортом на батч (P6: не душимо стор по паспорту на виклик).
`record()` синхронний і дешевий — кличеться і з sync `LLMInterface`-стеку
(через `MeterLLM`), і з async `on_inference_stats` агентського шляху.
Best-effort: збій sink ніколи не ламає LLM-шлях. Retention для `kind:usage`
уже в політиці (`DEFAULT_RETENTION_DAYS["usage"] = 7`).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("jarvis.core.llm.usage")

# Sink отримує ГОТОВИЙ store-dict агрегат-паспорта (без user/org — їх додає wiring).
UsageSink = Callable[[dict[str, Any]], Awaitable[None]]

DEFAULT_BATCH_SIZE = 8


class _StatsSlot(threading.local):
    """Thread-local слот для сирих stats від адаптера (nested sync виклик)."""

    stats: dict[str, Any] | None = None


class UsageMeter:
    """Батч-акумулятор usage-подій; на повному батчі планує flush у sink."""

    def __init__(
        self,
        sink: UsageSink,
        *,
        source: str = "usage_meter",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._sink = sink
        self._source = source
        self._batch_size = max(1, batch_size)
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._tasks: set[asyncio.Task[int]] = set()
        self.slot = _StatsSlot()

    def record(
        self,
        *,
        model: str,
        tokens_out: int = 0,
        tokens_in: int = 0,
        duration_ms: float = 0.0,
        path: str = "chat",
    ) -> None:
        """Додає подію (sync, дешево). Повний батч → фонова відправка."""
        ev = {
            "model": (model or "unknown").strip() or "unknown",
            "tokens_out": max(0, int(tokens_out)),
            "tokens_in": max(0, int(tokens_in)),
            "duration_ms": max(0.0, round(float(duration_ms), 1)),
            "path": path,
        }
        with self._lock:
            self._events.append(ev)
            full = len(self._events) >= self._batch_size
        if full:
            self._spawn_flush()

    def record_ollama_stats(self, stats: dict[str, Any], *, path: str = "agent") -> None:
        """Зручний вхід для `on_inference_stats` (див. `parsers.ollama_inference_stats`)."""
        try:
            ec = int(stats.get("eval_count") or 0)
            ed_ns = int(stats.get("eval_duration_ns") or 0)
            pec = int(stats.get("prompt_eval_count") or 0)
        except (TypeError, ValueError):
            return
        self.record(
            model=str(stats.get("model") or ""),
            tokens_out=ec,
            tokens_in=pec,
            duration_ms=ed_ns / 1e6,
            path=path,
        )

    def _spawn_flush(self) -> None:
        try:
            task = asyncio.get_running_loop().create_task(self.flush())
        except RuntimeError:
            # Sync-контекст без loop: події лишаються в буфері до наступного
            # record/flush з loop-контексту (usage не вартий блокування).
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> int:
        """Відправляє накопичене одним агрегат-паспортом. Повертає к-сть подій."""
        with self._lock:
            batch, self._events = self._events, []
        if not batch:
            return 0
        store = aggregate_usage_store(batch, source=self._source)
        try:
            await self._sink(store)
        except Exception as exc:  # noqa: BLE001 — метрика нефатальна
            logger.debug("usage flush failed: %s", exc)
            return 0
        return len(batch)

    async def drain(self) -> None:
        """Флаш + дочекатися фонових відправок (тести/shutdown)."""
        await self.flush()
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


def aggregate_usage_store(
    events: list[dict[str, Any]], *, source: str = "usage_meter"
) -> dict[str, Any]:
    """Батч подій → ОДИН store-dict `kind:usage` (агрегат; консюмери сумують payload).

    Без user/org — wiring (tools/gateway) додає партицію перед ingest.
    """
    calls = len(events)
    tok_out = sum(int(e.get("tokens_out") or 0) for e in events)
    tok_in = sum(int(e.get("tokens_in") or 0) for e in events)
    by_model: dict[str, dict[str, Any]] = {}
    for e in events:
        m = str(e.get("model") or "unknown")
        slot = by_model.setdefault(m, {"calls": 0, "tokens_out": 0, "tokens_in": 0, "ms": 0.0})
        slot["calls"] += 1
        slot["tokens_out"] += int(e.get("tokens_out") or 0)
        slot["tokens_in"] += int(e.get("tokens_in") or 0)
        slot["ms"] = round(slot["ms"] + float(e.get("duration_ms") or 0.0), 1)
    summary = (
        f"LLM usage: {calls} викл., {tok_out} tok out / {tok_in} tok in, "
        f"{len(by_model)} мод."
    )
    return {
        "kind": "usage",
        "summary": summary,
        "tags": ["module:llm"],
        "source": source,
        "sensitivity": "public",
        "payload": {
            "calls": calls,
            "tokens_out": tok_out,
            "tokens_in": tok_in,
            "by_model": by_model,
        },
    }
