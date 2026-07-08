"""OpenAICompatAdapter + openai_delta + build_llm_stack(openai) — opt-in хмара (S1)."""
from __future__ import annotations

import httpx
import pytest

from jarvis_core.llm.adapters import OpenAICompatAdapter
from jarvis_core.llm.decorators import build_llm_stack
from jarvis_core.llm.parsers import openai_delta


# --- парсер SSE ---
def test_openai_delta_content():
    assert openai_delta('data: {"choices":[{"delta":{"content":"Привіт"}}]}') == ("Привіт", False)


def test_openai_delta_done_marker():
    assert openai_delta("data: [DONE]") == ("", True)


def test_openai_delta_finish_reason():
    line = 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
    assert openai_delta(line) == ("", True)


@pytest.mark.parametrize(
    "line",
    [
        "", "data:", "data: not-json", 'data: {"choices":[]}', "data: {}",
        # валідний JSON, але НЕ обʼєкт (keepalive/масив/рядок) — не має падати з AttributeError
        "data: null", 'data: "keepalive"', "data: [1,2]", "data: 42",
        # choices не список
        'data: {"choices":{"0":{"delta":{"content":"x"}}}}',
    ],
)
def test_openai_delta_robust(line: str):
    assert openai_delta(line) == ("", False)


def test_generate_choices_as_object_returns_empty():
    # малформед провайдер: choices — обʼєкт, не масив → порожній рядок, не KeyError
    ad_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"choices": {"0": {"message": {"content": "x"}}}})
        )
    )
    assert OpenAICompatAdapter("https://api.x/v1", "m", client=ad_client).generate("q") == ""


# --- адаптер через MockTransport ---
def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_extracts_message_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer sk-test"
        body = request.read().decode()
        assert '"stream":false' in body and '"model":"gpt-x"' in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "42"}}]})

    ad = OpenAICompatAdapter("https://api.x/v1", "gpt-x", api_key="sk-test", client=_client(handler))
    assert ad.generate("2+2?") == "42"


def test_generate_no_key_omits_auth_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    ad = OpenAICompatAdapter("http://localhost:8000/v1", "local", client=_client(handler))
    assert ad.generate("hi") == "ok"


def test_generate_empty_choices_returns_empty():
    ad = OpenAICompatAdapter(
        "https://api.x/v1", "m", client=_client(lambda r: httpx.Response(200, json={"choices": []}))
    )
    assert ad.generate("x") == ""


def test_stream_yields_deltas_until_done():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        "data: [DONE]\n\n"
        'data: {"choices":[{"delta":{"content":"ignored-after-done"}}]}\n\n'
    )
    ad = OpenAICompatAdapter(
        "https://api.x/v1", "m",
        client=_client(lambda r: httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})),
    )
    assert "".join(ad.stream("hi")) == "Hello"


def test_base_url_trailing_slash_normalized():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"choices": [{"message": {"content": "y"}}]})

    OpenAICompatAdapter("https://api.x/v1/", "m", client=_client(handler)).generate("q")
    assert seen["path"] == "/v1/chat/completions"


# --- інтеграція в стек ---
def test_build_llm_stack_openai_backend_end_to_end():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "sonnet-says-hi"}}]})

    llm = build_llm_stack(
        backend="openai",
        openai_base_url="https://api.x/v1",
        openai_model="gpt-4o-mini",
        openai_api_key="sk-1",
        client=_client(handler),
        style_prefix="",
    )
    assert llm.generate("hello") == "sonnet-says-hi"


def test_build_llm_stack_openai_requires_base_url():
    with pytest.raises(ValueError, match="CLOUD_LLM_BASE_URL"):
        build_llm_stack(backend="openai", openai_model="gpt-x")


def test_default_backend_stays_ollama_not_cloud():
    """S1-регресія: без явного backend хмара не піднімається (дефолт ollama)."""
    import inspect

    sig = inspect.signature(build_llm_stack)
    assert sig.parameters["backend"].default == "ollama"
