import httpx

from jarvis_core.llm.adapters import KoboldAdapter
from jarvis_core.llm.decorators import CacheLLM, StyleLLM, build_llm_stack
from jarvis_core.llm.parsers import kobold_token, ollama_chunk


def test_parsers():
    assert kobold_token('data: {"token": "а"}') == "а"
    assert ollama_chunk('{"response": "x", "done": true}') == ("x", True)


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
