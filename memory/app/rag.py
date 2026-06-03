"""RAG: чанкінг тексту + ембединги через Ollama."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jarvis.memory.rag")


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """Ділить текст на частини <= max_chars з перекриттям overlap символів."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    step = max(1, max_chars - overlap)
    while start < n:
        chunks.append(text[start : start + max_chars])
        start += step
    return chunks


class Embedder:
    def __init__(self, ollama_host: str, model: str, timeout: float = 60.0) -> None:
        self._url = f"{ollama_host.rstrip('/')}/api/embeddings"
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(self._url, json={"model": self._model, "prompt": text})
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValueError(f"unexpected embeddings response: {data!r}")
        return [float(x) for x in emb]
