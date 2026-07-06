from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from jarvis_core.llm.interface import LLMInterface
from jarvis_core.llm.parsers import kobold_token, ollama_chunk

# SY-6: адаптер — єдине місце, де видно сирі inference-stats бекенда (eval_count…).
# Репортить їх нагору (MeterLLM) синхронним колбеком; None = метрика вимкнена.
StatsFn = Callable[[dict[str, Any]], None]


class KoboldAdapter(LLMInterface):
    def __init__(
        self, base_url: str, client: httpx.Client | None = None, timeout: float = 180.0
    ) -> None:
        self._url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        resp = self._client.post(
            f"{self._url}/api/v1/generate",
            json={"prompt": prompt, "max_length": max_tokens},
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return str(results[0].get("text", "")) if results else ""

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        with self._client.stream(
            "POST",
            f"{self._url}/api/extra/generate/stream",
            json={"prompt": prompt, "max_length": max_tokens},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                tok = kobold_token(line)
                if tok:
                    yield tok


class OllamaAdapter(LLMInterface):
    def __init__(
        self,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
        timeout: float = 180.0,
        on_stats: StatsFn | None = None,
    ) -> None:
        self._url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)
        self._on_stats = on_stats

    def _report(self, data: dict[str, Any]) -> None:
        if self._on_stats is None:
            return
        try:
            self._on_stats(data)
        except Exception:  # noqa: BLE001 — метрика не ламає генерацію
            pass

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        resp = self._client.post(
            f"{self._url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            self._report(data)
            return str(data.get("response", ""))
        return ""

    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        with self._client.stream(
            "POST",
            f"{self._url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": True,
                "options": {"num_predict": max_tokens},
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                text, done = ollama_chunk(line)
                if text:
                    yield text
                if done:
                    # Фінальний NDJSON-рядок несе eval_count/prompt_eval_count.
                    try:
                        final = json.loads(line.strip())
                    except (json.JSONDecodeError, AttributeError):
                        final = None
                    if isinstance(final, dict):
                        self._report(final)
                    break
