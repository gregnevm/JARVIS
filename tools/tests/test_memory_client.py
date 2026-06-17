"""MemoryClient толерує помилки Memory-сервісу (памʼять — не критичний шлях)."""
import httpx

from app.memory_client import MemoryClient


class _OKResp:
    def raise_for_status(self) -> None:
        ...

    def json(self) -> dict:
        return {"results": [{"content": "ctx"}]}


class _OKClient:
    async def post(self, *a, **k):
        return _OKResp()


class _BoomClient:
    async def post(self, *a, **k):
        raise httpx.HTTPError("memory down")


async def test_search_success():
    mc = MemoryClient("http://memory:8100")
    mc._client = _OKClient()
    assert await mc.search(1, "q") == [{"content": "ctx"}]


async def test_search_tolerates_error():
    mc = MemoryClient("http://memory:8100")
    mc._client = _BoomClient()
    assert await mc.search(1, "q") == []


async def test_store_tolerates_error():
    mc = MemoryClient("http://memory:8100")
    mc._client = _BoomClient()
    await mc.store(1, "hi")  # не має кидати винятків


class _CtxResp:
    def raise_for_status(self) -> None: ...

    def json(self) -> dict:
        return {"results": [{"summary": "купив молоко", "tags": ["kind:note"]}]}


class _CtxClient:
    async def post(self, *a, **k):
        return _CtxResp()


async def test_search_context_success():
    mc = MemoryClient("http://memory:8100")
    mc._client = _CtxClient()
    out = await mc.search_context(1, "молоко")
    assert out == [{"summary": "купив молоко", "tags": ["kind:note"]}]


async def test_search_context_tolerates_error():
    mc = MemoryClient("http://memory:8100")
    mc._client = _BoomClient()
    assert await mc.search_context(1, "q") == []
