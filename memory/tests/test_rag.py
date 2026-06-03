"""chunk_text — чанкінг тексту з перекриттям + кеш ембедингів."""
from typing import Any

from app.rag import Embedder, chunk_text


def test_empty():
    assert chunk_text("") == []


def test_whitespace_only():
    assert chunk_text("   \n  ") == []


def test_short_single_chunk():
    assert chunk_text("короткий текст") == ["короткий текст"]


def test_long_text_with_overlap():
    text = "".join(str(i % 10) for i in range(1000))  # 1000 символів
    chunks = chunk_text(text, max_chars=400, overlap=100)  # крок = 300
    assert len(chunks) == 4
    assert chunks[0] == text[:400]
    assert chunks[1] == text[300:700]  # перекриття 100
    assert chunks[-1] == text[900:1000]
    assert all(len(c) <= 400 for c in chunks)


# --- кеш ембедингів ---
class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, name: str) -> Any:
        return self.store.get(name)

    async def set(self, name: str, value: str, ex: int) -> None:
        self.store[name] = value


class _FakeResp:
    def __init__(self, emb: list[float]) -> None:
        self._emb = emb

    def raise_for_status(self) -> None: ...

    def json(self) -> dict[str, Any]:
        return {"embedding": self._emb}


class _FakeHTTP:
    def __init__(self, emb: list[float]) -> None:
        self.calls = 0
        self._emb = emb

    async def post(self, *a: Any, **k: Any) -> _FakeResp:
        self.calls += 1
        return _FakeResp(self._emb)


async def test_embed_cache_miss_then_hit():
    e = Embedder("http://x", "m", redis=_FakeRedis())
    e._client = _FakeHTTP([0.1, 0.2, 0.3])  # type: ignore[assignment]
    v1 = await e.embed("привіт")
    assert v1 == [0.1, 0.2, 0.3]
    assert e._client.calls == 1  # перший раз — порахували
    v2 = await e.embed("привіт")
    assert v2 == [0.1, 0.2, 0.3]
    assert e._client.calls == 1  # другий раз — з кешу, в Ollama не ходили


async def test_embed_without_redis_always_computes():
    e = Embedder("http://x", "m", redis=None)
    e._client = _FakeHTTP([1.0, 2.0])  # type: ignore[assignment]
    await e.embed("a")
    await e.embed("a")
    assert e._client.calls == 2  # без кешу — щоразу запит


async def test_embed_cache_failopen_on_redis_error():
    class _BoomRedis:
        async def get(self, name: str) -> Any:
            raise RuntimeError("redis down")

        async def set(self, name: str, value: str, ex: int) -> None:
            raise RuntimeError("redis down")

    e = Embedder("http://x", "m", redis=_BoomRedis())
    e._client = _FakeHTTP([5.0])  # type: ignore[assignment]
    v = await e.embed("x")  # не має кидати, попри биту redis
    assert v == [5.0]
