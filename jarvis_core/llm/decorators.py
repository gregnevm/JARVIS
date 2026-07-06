from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import httpx

from jarvis_core.llm.adapters import KoboldAdapter, OllamaAdapter
from jarvis_core.llm.interface import LLMInterface
from jarvis_core.llm.jsonl_log import JsonlLog


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


JARVIS_STYLE_PREFIX = (
    "Ти JARVIS — лаконічний україномовний помічник. Відповідай стисло і по суті."
)


def build_llm_stack(
    *,
    backend: Literal["ollama", "kobold"] = "ollama",
    ollama_host: str = "http://127.0.0.1:11434",
    ollama_model: str = "qwen2.5:7b-instruct",
    kobold_host: str = "http://127.0.0.1:5001",
    timeout: float = 180.0,
    log_path: str | None = None,
    cache_ttl: float = 3600.0,
    retry_attempts: int = 3,
    style_prefix: str = JARVIS_STYLE_PREFIX,
    client: httpx.Client | None = None,
) -> LLMInterface:
    """Composition root: Style → Retry → Cache → Logging → Adapter."""
    base: LLMInterface
    if backend == "kobold":
        base = KoboldAdapter(kobold_host, client=client, timeout=timeout)
    else:
        base = OllamaAdapter(ollama_host, ollama_model, client=client, timeout=timeout)
    llm: LLMInterface = base
    if log_path:
        llm = LoggingLLM(llm, log_path)
    llm = CacheLLM(llm, ttl_sec=cache_ttl)
    llm = RetryLLM(llm, attempts=retry_attempts)
    llm = StyleLLM(llm, style_prefix)
    return llm
