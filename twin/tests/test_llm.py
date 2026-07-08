"""LLM adapter layer — KoboldAdapter / OllamaAdapter (httpx MockTransport, без мережі)."""
import json

import httpx
import pytest
from app.config import Settings, create_llm
from app.llm import (
    KoboldAdapter,
    LLMInterface,
    LoggingLLM,
    OllamaAdapter,
    _kobold_token,
    _ollama_chunk,
)
from app.session_log import JsonlLog


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- generate через MockTransport ---
def test_kobold_generate():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v1/generate"
        body = json.loads(req.content)
        assert body["prompt"] == "hi"
        assert body["max_length"] == 50
        return httpx.Response(200, json={"results": [{"text": "привіт"}]})

    a = KoboldAdapter("http://kobold:5001", client=_client(handler))
    assert a.generate("hi", 50) == "привіт"


def test_kobold_empty_results():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    assert KoboldAdapter("http://k", client=_client(handler)).generate("x") == ""


def test_ollama_generate():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/generate"
        body = json.loads(req.content)
        assert body["model"] == "qwen2.5:7b-instruct"
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 50
        return httpx.Response(200, json={"response": "відповідь", "done": True})

    a = OllamaAdapter("http://host:11434", "qwen2.5:7b-instruct", client=_client(handler))
    assert a.generate("hi", 50) == "відповідь"


def test_kobold_stream():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/extra/generate/stream"
        body = json.loads(req.content)
        assert body["max_length"] == 32
        lines = (
            'data: {"token": "а"}\n'
            'data: {"token": "б"}\n'
            "data: [DONE]\n"
        )
        return httpx.Response(200, text=lines)

    a = KoboldAdapter("http://kobold:5001", client=_client(handler))
    assert list(a.stream("hi", 32)) == ["а", "б"]


def test_ollama_stream():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/generate"
        body = json.loads(req.content)
        assert body["stream"] is True
        assert body["options"]["num_predict"] == 16
        ndjson = (
            '{"response": "one", "done": false}\n'
            '{"response": "two", "done": true}\n'
        )
        return httpx.Response(200, text=ndjson)

    a = OllamaAdapter("http://host:11434", "m", client=_client(handler))
    assert list(a.stream("hi", 16)) == ["one", "two"]


def test_generate_http_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        KoboldAdapter("http://k", client=_client(handler)).generate("x")


# --- LSP: обидва взаємозамінні як LLMInterface ---
def test_create_llm_ollama():
    cfg = Settings(llm_backend="ollama", ollama_host="http://h", ollama_model="m")
    llm = create_llm(cfg)
    # build_llm_stack wraps Style → … → OllamaAdapter
    from jarvis_core.llm.decorators import StyleLLM

    assert isinstance(llm, StyleLLM)


def test_create_llm_kobold():
    from jarvis_core.llm.decorators import StyleLLM

    cfg = Settings(llm_backend="kobold", kobold_host="http://k")
    assert isinstance(create_llm(cfg), StyleLLM)


def test_settings_accepts_shared_openai_backend_without_crash():
    # СПІЛЬНИЙ LLM_BACKEND=openai (для tools) не має валити валідацію твіна…
    cfg = Settings(llm_backend="openai", ollama_host="http://h", ollama_model="m")
    assert cfg.llm_backend == "openai"


def test_create_llm_coerces_openai_to_ollama():
    # …і твін (без CLOUD_LLM_*) відкатується на ollama-стек, не падаючи на build.
    from jarvis_core.llm.decorators import StyleLLM

    cfg = Settings(llm_backend="openai", ollama_host="http://h", ollama_model="m")
    assert isinstance(create_llm(cfg), StyleLLM)


def test_logging_llm_writes_jsonl(tmp_path):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"text": "x"}]})

    inner = KoboldAdapter("http://k", client=_client(handler))
    log_path = tmp_path / "infer.jsonl"
    wrapped = LoggingLLM(inner, log_path=str(log_path))
    assert wrapped.generate("p") == "x"
    assert JsonlLog(log_path).count() == 1


def test_both_are_llm_interface():
    assert isinstance(KoboldAdapter("http://k"), LLMInterface)
    assert isinstance(OllamaAdapter("http://h", "m"), LLMInterface)


# --- чисті парсери потоків ---
def test_kobold_token_parse():
    assert _kobold_token('data: {"token": "це"}') == "це"
    assert _kobold_token('{"token": "те"}') == "те"
    assert _kobold_token("data: [DONE]") == ""
    assert _kobold_token("сміття") == ""
    assert _kobold_token("") == ""


def test_ollama_chunk_parse():
    assert _ollama_chunk('{"response": "сло", "done": false}') == ("сло", False)
    assert _ollama_chunk('{"response": "", "done": true}') == ("", True)
    assert _ollama_chunk("bad json") == ("", False)
    assert _ollama_chunk("") == ("", False)
