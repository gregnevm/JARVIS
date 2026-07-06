"""SY-6: UsageMeter/MeterLLM — батч-агрегація kind:usage, кеш не рахується."""
from __future__ import annotations

import json
from typing import Any

import httpx

from jarvis_core.llm.decorators import MeterLLM, build_llm_stack
from jarvis_core.llm.usage import UsageMeter, aggregate_usage_store


class _SinkSpy:
    def __init__(self) -> None:
        self.stores: list[dict[str, Any]] = []
        self.fail = False

    async def __call__(self, store: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("sink down")
        self.stores.append(store)


# --- агрегат-паспорт ---

def test_aggregate_usage_store_shape():
    events = [
        {"model": "m1", "tokens_out": 10, "tokens_in": 5, "duration_ms": 100.0, "path": "chat"},
        {"model": "m1", "tokens_out": 20, "tokens_in": 0, "duration_ms": 50.0, "path": "agent"},
        {"model": "m2", "tokens_out": 1, "tokens_in": 1, "duration_ms": 5.0, "path": "chat"},
    ]
    store = aggregate_usage_store(events, source="test_meter")
    assert store["kind"] == "usage" and store["source"] == "test_meter"
    assert "module:llm" in store["tags"]
    p = store["payload"]
    assert p["calls"] == 3 and p["tokens_out"] == 31 and p["tokens_in"] == 6
    assert p["by_model"]["m1"]["calls"] == 2 and p["by_model"]["m1"]["tokens_out"] == 30
    assert p["by_model"]["m2"]["tokens_in"] == 1


# --- UsageMeter ---

async def test_meter_flush_sends_one_aggregate():
    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=100)
    meter.record(model="m1", tokens_out=10, duration_ms=5.0)
    meter.record(model="m1", tokens_out=7)
    assert await meter.flush() == 2
    assert len(sink.stores) == 1  # один паспорт на батч, не по одному на виклик
    assert sink.stores[0]["payload"]["tokens_out"] == 17
    assert await meter.flush() == 0  # порожньо — нічого не шле


async def test_meter_full_batch_spawns_background_flush():
    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=2)
    meter.record(model="m1", tokens_out=1)
    meter.record(model="m1", tokens_out=2)  # батч повний → фонова відправка
    await meter.drain()
    assert len(sink.stores) == 1 and sink.stores[0]["payload"]["calls"] == 2


async def test_meter_sink_failure_swallowed():
    sink = _SinkSpy()
    sink.fail = True
    meter = UsageMeter(sink, batch_size=100)
    meter.record(model="m1", tokens_out=1)
    assert await meter.flush() == 0  # collапс sink не піднімається (best-effort)


async def test_record_ollama_stats_mapping():
    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=100)
    meter.record_ollama_stats(
        {"model": "m1", "eval_count": 42, "eval_duration_ns": 2_000_000_000, "prompt_eval_count": 7},
        path="agent",
    )
    await meter.flush()
    p = sink.stores[0]["payload"]
    assert p["tokens_out"] == 42 and p["tokens_in"] == 7
    assert p["by_model"]["m1"]["ms"] == 2000.0


# --- MeterLLM ---

class _StubLLM:
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        return "ok"

    def stream(self, prompt: str, max_tokens: int = 512):
        yield "ok"


async def test_meterllm_records_latency_without_backend_stats():
    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=100)
    llm = MeterLLM(_StubLLM(), meter, model="stub")
    assert llm.generate("p") == "ok"
    await meter.flush()
    ev = sink.stores[0]["payload"]["by_model"]["stub"]
    assert ev["calls"] == 1 and ev["tokens_out"] == 0  # без stats — лише латентність


async def test_full_stack_meters_real_calls_but_not_cache_hits():
    """e2e sync-шляху: адаптер → слот → MeterLLM; кеш-хіт не коштує токенів."""
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "response": "відповідь",
            "model": "m1",
            "eval_count": 11,
            "prompt_eval_count": 4,
            "eval_duration": 1_000_000_000,
        })

    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=100)
    llm = build_llm_stack(
        ollama_host="http://o", ollama_model="m1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        usage_meter=meter, style_prefix="",
    )
    assert llm.generate("питання") == "відповідь"
    assert llm.generate("питання") == "відповідь"  # кеш-хіт — без виклику бекенда
    await meter.flush()
    assert len(sink.stores) == 1
    p = sink.stores[0]["payload"]
    assert p["calls"] == 1  # НЕ 2: кеш-хіт не метриться (SY-6 — токени = реальна робота)
    assert p["tokens_out"] == 11 and p["tokens_in"] == 4


async def test_stack_stream_reports_final_chunk_stats():
    lines = [
        json.dumps({"response": "а", "done": False}),
        json.dumps({
            "response": "", "done": True,
            "model": "m1", "eval_count": 3, "prompt_eval_count": 2,
            "eval_duration": 500_000_000,
        }),
    ]

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="\n".join(lines).encode())

    sink = _SinkSpy()
    meter = UsageMeter(sink, batch_size=100)
    llm = build_llm_stack(
        ollama_host="http://o", ollama_model="m1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        usage_meter=meter, style_prefix="",
    )
    assert "".join(llm.stream("х")) == "а"
    await meter.flush()
    p = sink.stores[0]["payload"]
    assert p["tokens_out"] == 3 and p["tokens_in"] == 2
