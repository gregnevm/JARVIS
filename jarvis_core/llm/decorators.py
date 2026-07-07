from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import httpx

from jarvis_core.llm.adapters import KoboldAdapter, OllamaAdapter, OpenAICompatAdapter
from jarvis_core.llm.interface import LLMInterface
from jarvis_core.llm.jsonl_log import JsonlLog
from jarvis_core.llm.parsers import ollama_inference_stats
from jarvis_core.llm.usage import UsageMeter


class LoggingLLM(LLMInterface):
    def __init__(self, inner: LLMInterface, log_path: str | Path | None = None) -> None:
        self._inner = inner
        self._log_path = Path(log_path) if log_path else None

    def _record(self, event: dict[str, object]) -> None:
        if self._log_path:
            JsonlLog(self._log_path).append(event)

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        out = self._inner.generate(prompt, max_tokens)
        self._record({"op": "generate", "max_tokens": max_tokens, "len": len(out)})
        return out

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        parts: list[str] = []
        for tok in self._inner.stream(prompt, max_tokens):
            parts.append(tok)
            yield tok
        self._record({"op": "stream", "max_tokens": max_tokens, "len": sum(len(p) for p in parts)})


class CacheLLM(LLMInterface):
    def __init__(self, inner: LLMInterface, ttl_sec: float = 3600.0) -> None:
        self._inner = inner
        self._ttl = ttl_sec
        self._store: dict[str, tuple[float, str]] = {}

    def _key(self, prompt: str, max_tokens: int) -> str:
        raw = f"{max_tokens}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if not entry:
            return None
        ts, val = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return val

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        key = self._key(prompt, max_tokens)
        hit = self._get(key)
        if hit is not None:
            return hit
        out = self._inner.generate(prompt, max_tokens)
        self._store[key] = (time.monotonic(), out)
        return out

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        yield from self._inner.stream(prompt, max_tokens)


class RetryLLM(LLMInterface):
    def __init__(self, inner: LLMInterface, attempts: int = 3, base_delay: float = 1.0) -> None:
        self._inner = inner
        self._attempts = max(1, attempts)
        self._base_delay = base_delay

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        last: Exception | None = None
        for i in range(self._attempts):
            try:
                return self._inner.generate(prompt, max_tokens)
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if i < self._attempts - 1:
                    time.sleep(self._base_delay * (2**i))
        if last:
            raise last
        return ""

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        yield from self._inner.stream(prompt, max_tokens)


class StyleLLM(LLMInterface):
    """Додає system-префікс до сирого prompt (DESIGN persona layer)."""

    def __init__(self, inner: LLMInterface, system_prefix: str) -> None:
        self._inner = inner
        self._prefix = system_prefix.strip()

    def _wrap(self, prompt: str) -> str:
        if not self._prefix:
            return prompt
        return f"{self._prefix}\n\n{prompt}"

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        return self._inner.generate(self._wrap(prompt), max_tokens)

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        yield from self._inner.stream(self._wrap(prompt), max_tokens)


class MeterLLM(LLMInterface):
    """Лічильник як декоратор (SY-6): usage-подія на КОЖЕН реальний виклик бекенда.

    Сидить ПІД CacheLLM — кеш-хіт не коштує токенів і не рахується. Токени бере
    зі слота, який наповнює адаптер (`on_stats`, той самий thread у nested
    sync-виклику); бекенд без stats (kobold) → лише model+latency (tokens 0).
    """

    def __init__(self, inner: LLMInterface, meter: UsageMeter, *, model: str, path: str = "chat") -> None:
        self._inner = inner
        self._meter = meter
        self._model = model
        self._path = path

    def _note_stats(self, raw: dict[str, Any]) -> None:
        """Колбек для адаптера: сирий json бекенда → thread-local слот."""
        self._meter.slot.stats = ollama_inference_stats(raw)

    def _flush_slot(self, fallback_ms: float) -> None:
        stats = self._meter.slot.stats
        self._meter.slot.stats = None
        if stats:
            self._meter.record(
                model=str(stats.get("model") or self._model),
                tokens_out=int(stats.get("eval_count") or 0),
                tokens_in=int(stats.get("prompt_eval_count") or 0),
                duration_ms=int(stats.get("eval_duration_ns") or 0) / 1e6,
                path=self._path,
            )
        else:
            self._meter.record(model=self._model, duration_ms=fallback_ms, path=self._path)

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        self._meter.slot.stats = None
        t0 = time.monotonic()
        out = self._inner.generate(prompt, max_tokens)
        self._flush_slot((time.monotonic() - t0) * 1000)
        return out

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        self._meter.slot.stats = None
        t0 = time.monotonic()
        yield from self._inner.stream(prompt, max_tokens)
        self._flush_slot((time.monotonic() - t0) * 1000)


JARVIS_STYLE_PREFIX = (
    "Ти JARVIS — лаконічний україномовний помічник. Відповідай стисло і по суті."
)


def build_llm_stack(
    *,
    backend: Literal["ollama", "kobold", "openai"] = "ollama",
    ollama_host: str = "http://127.0.0.1:11434",
    ollama_model: str = "qwen2.5:7b-instruct",
    kobold_host: str = "http://127.0.0.1:5001",
    openai_base_url: str = "",
    openai_model: str = "",
    openai_api_key: str = "",
    timeout: float = 180.0,
    log_path: str | None = None,
    cache_ttl: float = 3600.0,
    retry_attempts: int = 3,
    style_prefix: str = JARVIS_STYLE_PREFIX,
    client: httpx.Client | None = None,
    usage_meter: UsageMeter | None = None,
) -> LLMInterface:
    """Composition root: Style → Retry → Cache → [Meter] → Logging → Adapter.

    `usage_meter` (SY-6, опційно): шар MeterLLM під Cache — usage-паспорти лише
    за реальні виклики бекенда; адаптер репортить у нього сирі stats (токени).

    `backend="openai"` (opt-in, S1): OpenAI-сумісна хмара/локальний vLLM за тим
    самим інтерфейсом (`meter_model` бере openai_model). Порожній base_url при
    цьому backend → ValueError (fail-fast, щоб не бити нікуди мовчки)."""
    base: LLMInterface
    meter_layer: MeterLLM | None = None
    meter_model = ollama_model

    def _relay_stats(raw: dict[str, Any]) -> None:
        # Слот наповнює адаптер; шар Meter створюється нижче — late-bound closure.
        if meter_layer is not None:
            meter_layer._note_stats(raw)

    if backend == "kobold":
        base = KoboldAdapter(kobold_host, client=client, timeout=timeout)
    elif backend == "openai":
        if not openai_base_url:
            raise ValueError("LLM_BACKEND=openai потребує CLOUD_LLM_BASE_URL (fail-fast)")
        meter_model = openai_model or "openai"
        base = OpenAICompatAdapter(
            openai_base_url, openai_model, api_key=openai_api_key,
            client=client, timeout=timeout,
        )
    else:
        base = OllamaAdapter(
            ollama_host, ollama_model, client=client, timeout=timeout,
            on_stats=_relay_stats if usage_meter is not None else None,
        )
    llm: LLMInterface = base
    if log_path:
        llm = LoggingLLM(llm, log_path)
    if usage_meter is not None:
        meter_layer = MeterLLM(llm, usage_meter, model=meter_model)
        llm = meter_layer
    llm = CacheLLM(llm, ttl_sec=cache_ttl)
    llm = RetryLLM(llm, attempts=retry_attempts)
    llm = StyleLLM(llm, style_prefix)
    return llm
