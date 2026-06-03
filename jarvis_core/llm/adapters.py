from __future__ import annotations

from collections.abc import Iterator

import httpx

from jarvis_core.llm.interface import LLMInterface
from jarvis_core.llm.parsers import kobold_token, ollama_chunk


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
    ) -> None:
        self._url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

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
        return str(resp.json().get("response", ""))

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
                    break
