"""Observability: turn/tool latency, RAG hit rate (Фаза 5.3) → Redis rolling window.

Ключі org-префіксовані через `redis_key` (AGENTS.md §5 multi-tenant discipline;
SAAS_DEEP_DIVE §0.2 per-org metrics — AP-4.4). `org_id=None` дає legacy unscoped
форму `jarvis:metrics:*` — байт-у-байт як до розщеплення, тож self-hosted
(синтетичний org) не змінює поведінку (S2). Реальний `org_id` дає per-org
розщеплення `jarvis:{org}:metrics:*`; підключиться, коли tenant-ctx доходитиме до
tools (`RequestContext.to_headers`, ще не wired — див. `jarvis_core/context.py`).
"""
from __future__ import annotations

import logging
from typing import Any

from jarvis_core.context import redis_key

from .redis_util import get_redis

logger = logging.getLogger("jarvis.tools.metrics")

_MAX_SAMPLES = 200


def _mkey(org_id: str | None, *parts: str) -> str:
    """Org-scoped metrics key: `redis_key(org, "metrics", *parts)`.

    `org_id=None` → `jarvis:metrics:{parts}` (legacy unscoped, S2-safe default)."""
    return redis_key(org_id, "metrics", *parts)


def _percentiles(values: list[int]) -> dict[str, int | float]:
    if not values:
        return {"count": 0, "p50_ms": 0, "p95_ms": 0, "avg_ms": 0}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> int:
        idx = min(n - 1, max(0, int(n * p) - 1))
        return int(s[idx])

    return {
        "count": n,
        "p50_ms": pct(0.5),
        "p95_ms": pct(0.95),
        "avg_ms": round(sum(s) / n, 1),
    }


async def _push_list(key: str, value: str) -> None:
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.lpush(key, value)
        pipe.ltrim(key, 0, _MAX_SAMPLES - 1)
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics push failed: %s", exc)


def _percentiles_float(values: list[float]) -> dict[str, int | float]:
    if not values:
        return {"count": 0, "p50": 0.0, "p95": 0.0, "avg": 0.0}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(n * p) - 1))
        return round(s[idx], 1)

    return {
        "count": n,
        "p50": pct(0.5),
        "p95": pct(0.95),
        "avg": round(sum(s) / n, 1),
    }


async def record_inference(
    model: str, eval_count: int, eval_duration_ns: int, *, org_id: str | None = None
) -> None:
    if eval_count <= 0 or eval_duration_ns <= 0:
        return
    tok_s = eval_count / (eval_duration_ns / 1e9)
    model = (model or "unknown").strip() or "unknown"
    await _push_list(_mkey(org_id, "tok_s"), f"{tok_s:.2f}|{model}")


async def record_turn(
    duration_ms: float, mode: str, iters: int = 0, *, org_id: str | None = None
) -> None:
    ms = max(0, int(duration_ms))
    await _push_list(_mkey(org_id, "turns"), f"{ms}|{mode}|{iters}")


async def record_tool(name: str, duration_ms: float, *, org_id: str | None = None) -> None:
    if not name:
        return
    ms = max(0, int(duration_ms))
    await _push_list(_mkey(org_id, "tool_lat", name), str(ms))


async def record_rag(hits: int, queried: bool = True, *, org_id: str | None = None) -> None:
    if not queried:
        return
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.incr(_mkey(org_id, "rag_queries"))
        if hits > 0:
            pipe.incr(_mkey(org_id, "rag_hits"))
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics rag failed: %s", exc)


async def summary(*, org_id: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "turn_ms": {"count": 0, "p50_ms": 0, "p95_ms": 0, "avg_ms": 0},
        "tok_s": {"count": 0, "p50": 0.0, "p95": 0.0, "avg": 0.0},
        "rag_hit_rate": 0.0,
        "rag_queries": 0,
        "tools": {},
    }
    try:
        r = get_redis()
        raw_turns = await r.lrange(_mkey(org_id, "turns"), 0, _MAX_SAMPLES - 1)
        turn_ms: list[int] = []
        for line in raw_turns or []:
            part = str(line).split("|", 1)[0]
            try:
                turn_ms.append(int(part))
            except ValueError:
                continue
        out["turn_ms"] = _percentiles(turn_ms)

        raw_toks = await r.lrange(_mkey(org_id, "tok_s"), 0, _MAX_SAMPLES - 1)
        tok_vals: list[float] = []
        for line in raw_toks or []:
            part = str(line).split("|", 1)[0]
            try:
                tok_vals.append(float(part))
            except ValueError:
                continue
        out["tok_s"] = _percentiles_float(tok_vals)

        q = int(await r.get(_mkey(org_id, "rag_queries")) or 0)
        h = int(await r.get(_mkey(org_id, "rag_hits")) or 0)
        out["rag_queries"] = q
        out["rag_hit_rate"] = round(h / q, 3) if q else 0.0

        tools: dict[str, dict[str, Any]] = {}
        _tool_prefix = _mkey(org_id, "tool_lat") + ":"
        async for key in r.scan_iter(match=f"{_tool_prefix}*", count=50):
            name = str(key).replace(_tool_prefix, "", 1)
            samples = await r.lrange(key, 0, 99)
            vals: list[int] = []
            for s in samples or []:
                try:
                    vals.append(int(s))
                except ValueError:
                    continue
            if vals:
                tools[name] = _percentiles(vals)
        out["tools"] = dict(sorted(tools.items(), key=lambda x: -x[1].get("count", 0))[:8])
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics summary failed: %s", exc)
        out["error"] = str(exc)
    return out


