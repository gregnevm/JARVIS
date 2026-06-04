import json

import httpx
import pytest

from jarvis_core.llm.adapters import KoboldAdapter
from jarvis_core.llm.chat import OllamaChatBackend
from jarvis_core.llm.decorators import CacheLLM, StyleLLM, build_llm_stack
from jarvis_core.llm.parsers import kobold_token, ollama_chat_chunk, ollama_chunk


def test_parsers():
    assert kobold_token('data: {"token": "а"}') == "а"
    assert ollama_chunk('{"response": "x", "done": true}') == ("x", True)


def test_chat_chunk_parser():
    assert ollama_chat_chunk('{"message":{"content":"hi"},"done":false}') == ("hi", False)
    assert ollama_chat_chunk('{"message":{"content":""},"done":true}') == ("", True)
    assert ollama_chat_chunk("not json") == ("", False)
    assert ollama_chat_chunk("") == ("", False)


async def test_ollama_chat_stream_yields_deltas():
    lines = [
        json.dumps({"message": {"content": "При"}, "done": False}),
        json.dumps({"message": {"content": "віт"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]
    body = "\n".join(lines).encode()

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = OllamaChatBackend("http://o", client=client)
    out = [d async for d in backend.chat_stream("m", [{"role": "user", "content": "hi"}])]
    assert "".join(out) == "Привіт"
    await client.aclose()


async def test_ollama_chat_stream_trips_breaker_on_error():
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = OllamaChatBackend("http://o", client=client, fail_threshold=1)
    with pytest.raises(httpx.HTTPError):
        async for _ in backend.chat_stream("m", [{"role": "user", "content": "x"}]):
            pass
    assert backend._open_until > 0  # брейкер розімкнувся після помилки
    await client.aclose()


def test_cache_hits():
    calls = 0

    class Stub:
        def generate(self, prompt: str, max_tokens: int = 512) -> str:
            nonlocal calls
            calls += 1
            return "ok"

        def stream(self, prompt: str, max_tokens: int = 512):
            yield "a"

    cached = CacheLLM(Stub(), ttl_sec=60)
    assert cached.generate("p") == "ok"
    assert cached.generate("p") == "ok"
    assert calls == 1


def test_style_wraps():
    class Stub:
        def generate(self, prompt: str, max_tokens: int = 512) -> str:
            return prompt

        def stream(self, prompt: str, max_tokens: int = 512):
            yield prompt

    out = StyleLLM(Stub(), "SYS").generate("user")
    assert out.startswith("SYS")


def test_kobold_mock():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"text": "hi"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert KoboldAdapter("http://k", client=client).generate("x") == "hi"
