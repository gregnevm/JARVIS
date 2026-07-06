import json

import httpx
import pytest

from jarvis_core.llm.adapters import KoboldAdapter
from jarvis_core.llm.chat import OllamaChatBackend
from jarvis_core.llm.decorators import CacheLLM, StyleLLM
from jarvis_core.llm.parsers import (
    extract_json_object,
    kobold_token,
    ollama_chat_chunk,
    ollama_chunk,
    scan_balanced_json,
)


def test_parsers():
    assert kobold_token('data: {"token": "а"}') == "а"
    assert ollama_chunk('{"response": "x", "done": true}') == ("x", True)
    assert extract_json_object('```json\n{"ok": true}\n```') == {"ok": True}
    assert extract_json_object('prefix {"x": 1} suffix') == {"x": 1}
    assert extract_json_object("") is None


def test_extract_json_object_robust_to_prose_braces():
    # Регресія: rfind('}') хапав дужку з хвостової/провідної прози й мовчки
    # повертав None (тихий degrade плану/рев'ю). Тепер балансований скан.
    assert extract_json_object('{"x": 1} note: use the } bracket carefully') == {"x": 1}
    assert extract_json_object("Answer (see {options}): {\"x\": 1}") == {"x": 1}
    # вкладені об'єкти (сирі й у fence) лишаються цілими
    assert extract_json_object('{"a": {"b": 2}}') == {"a": {"b": 2}}
    assert extract_json_object('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
    # дужка всередині рядкового значення не ламає баланс
    assert extract_json_object('text {"a": "}"} tail') == {"a": "}"}
    # немає валідного об'єкта → None
    assert extract_json_object("no json here") is None
    assert extract_json_object("{unclosed") is None


def test_extract_json_object_malformed_outer_keeps_none_not_inner():
    # Регресія (review): малформед-outer (хвостова кома — типова помилка 7B),
    # що обгортає валідний inner, НЕ має повертати inner під-об'єкт — інакше
    # глушиться 1-step фолбек плану/рев'ю. Має бути None.
    assert extract_json_object('{"summary":"s","steps":[{"file":"a.py"}],}') is None
    # inner все ще НЕ протікає, навіть якщо він валідний окремо
    assert extract_json_object('{bad outer {"file":"a.py","action":"x"}}') is None


def test_extract_json_object_linear_on_wall_of_braces():
    # Регресія (review): багато незакритих '{' не мають давати O(n^2)
    # ре-скан від кожної дужки. Незакритий перший старт → одразу стоп.
    assert extract_json_object("{" * 8000) is None


def test_scan_balanced_json_ssot():
    # SSOT сканер (реюзається агент-лупом): баланс із урахуванням рядків/екранів.
    assert scan_balanced_json('{"a": 1}', 0) == ('{"a": 1}', 8)
    assert scan_balanced_json('{"a": "}"}', 0) == ('{"a": "}"}', 10)
    assert scan_balanced_json("{unclosed", 0) == (None, 0)
    obj, end = scan_balanced_json('pre {"x": {"y": 2}} post', 4)
    assert obj == '{"x": {"y": 2}}' and end == 19


def test_chat_chunk_parser():
    assert ollama_chat_chunk('{"message":{"content":"hi"},"done":false}') == ("hi", False, None)
    assert ollama_chat_chunk('{"message":{"content":""},"done":true}') == ("", True, None)
    assert ollama_chat_chunk(
        '{"message":{"content":""},"done":true,"eval_count":100,"eval_duration":5000000000}'
    ) == ("", True, {"eval_count": 100, "eval_duration_ns": 5000000000, "model": ""})
    assert ollama_chat_chunk("not json") == ("", False, None)
    assert ollama_chat_chunk("") == ("", False, None)


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
