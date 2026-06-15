"""Observability: turn/tool latency, RAG hit rate (Фаза 5.3) → Redis rolling window."""
from __future__ import annotations

import logging
from typing import Any

from .redis_util import get_redis

logger = logging.getLogger("jarvis.tools.metrics")

_TURNS = "jarvis:metrics:turns"
_TOK_S = "jarvis:metrics:tok_s"
_RAG_Q = "jarvis:metrics:rag_queries"
_RAG_H = "jarvis:metrics:rag_hits"
_TOOL_LAT = "jarvis:metrics:tool_lat:"
_MAX_SAMPLES = 200


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


async def record_inference(model: str, eval_count: int, eval_duration_ns: int) -> None:
    if eval_count <= 0 or eval_duration_ns <= 0:
        return
    tok_s = eval_count / (eval_duration_ns / 1e9)
    model = (model or "unknown").strip() or "unknown"
    await _push_list(_TOK_S, f"{tok_s:.2f}|{model}")


async def record_turn(duration_ms: float, mode: str, iters: int = 0) -> None:
    ms = max(0, int(duration_ms))
    await _push_list(_TURNS, f"{ms}|{mode}|{iters}")


async def record_tool(name: str, duration_ms: float) -> None:
    if not name:
        return
    ms = max(0, int(duration_ms))
    await _push_list(f"{_TOOL_LAT}{name}", str(ms))


async def record_rag(hits: int, queried: bool = True) -> None:
    if not queried:
        return
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.incr(_RAG_Q)
        if hits > 0:
            pipe.incr(_RAG_H)
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics rag failed: %s", exc)


async def summary() -> dict[str, Any]:
    out: dict[str, Any] = {
        "turn_ms": {"count": 0, "p50_ms": 0, "p95_ms": 0, "avg_ms": 0},
        "tok_s": {"count": 0, "p50": 0.0, "p95": 0.0, "avg": 0.0},
        "rag_hit_rate": 0.0,
        "rag_queries": 0,
        "tools": {},
    }
    try:
        r = get_redis()
        raw_turns = await r.lrange(_TURNS, 0, _MAX_SAMPLES - 1)
        turn_ms: list[int] = []
        for line in raw_turns or []:
            part = str(line).split("|", 1)[0]
            try:
                turn_ms.append(int(part))
            except ValueError:
                continue
        out["turn_ms"] = _percentiles(turn_ms)

        raw_toks = await r.lrange(_TOK_S, 0, _MAX_SAMPLES - 1)
        tok_vals: list[float] = []
        for line in raw_toks or []:
            part = str(line).split("|", 1)[0]
            try:
                tok_vals.append(float(part))
            except ValueError:
                continue
        out["tok_s"] = _percentiles_float(tok_vals)

        q = int(await r.get(_RAG_Q) or 0)
        h = int(await r.get(_RAG_H) or 0)
        out["rag_queries"] = q
        out["rag_hit_rate"] = round(h / q, 3) if q else 0.0

        tools: dict[str, dict[str, Any]] = {}
        async for key in r.scan_iter(match=f"{_TOOL_LAT}*", count=50):
            name = str(key).replace(_TOOL_LAT, "", 1)
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


