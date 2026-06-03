"""RAG: чанкінг тексту + ембединги через Ollama (з опційним Redis-кешем)."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

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


class _RedisLike(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(self, name: str, value: str, ex: int) -> Any: ...


class Embedder:
    def __init__(
        self,
        ollama_host: str,
        model: str,
        timeout: float = 60.0,
        redis: _RedisLike | None = None,
        cache_ttl: int = 86400,
    ) -> None:
        self._url = f"{ollama_host.rstrip('/')}/api/embeddings"
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)
        self._redis = redis
        self._ttl = cache_ttl

    async def aclose(self) -> None:
        await self._client.aclose()

    def _cache_key(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"emb:{self._model}:{h}"

    async def _cache_get(self, key: str) -> list[float] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception as exc:  # noqa: BLE001 — кеш не критичний (fail-open)
            logger.warning("emb cache get failed (ignored): %s", exc)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return [float(x) for x in data]
        except (ValueError, TypeError):
            return None

    async def _cache_set(self, key: str, vec: list[float]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(vec), ex=self._ttl)
        except Exception as exc:  # noqa: BLE001 — кеш не критичний
            logger.warning("emb cache set failed (ignored): %s", exc)

    async def embed(self, text: str) -> list[float]:
        key = self._cache_key(text)
        cached = await self._cache_get(key)
        if cached is not None:
            return cached

        resp = await self._client.post(self._url, json={"model": self._model, "prompt": text})
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValueError(f"unexpected embeddings response: {data!r}")
        vec = [float(x) for x in emb]
        await self._cache_set(key, vec)
        return vec
