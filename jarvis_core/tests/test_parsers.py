"""Тести LLM-парсерів (jarvis_core.llm.parsers). Чисті, без мережі.

Парсери — критичний shared-core: `extract_json_object` живить tool-calling/OKR
агента (Стовп B), стрім-парсери — chat/agent цикл, `ollama_inference_stats` —
tok/s-телеметрію. test_llm_stack покривав лише happy-path; тут — guard-гілки
(не-dict JSON, вкладеність, [DONE], биті рядки, нульова/невалідна статистика).
"""
from __future__ import annotations

from jarvis_core.llm.parsers import (
    extract_json_object,
    kobold_token,
    ollama_chat_chunk,
    ollama_chunk,
    ollama_inference_stats,
)


class TestExtractJsonObject:
    def test_fenced_json(self) -> None:
        assert extract_json_object('```json\n{"ok": true}\n```') == {"ok": True}

    def test_fenced_without_lang(self) -> None:
        assert extract_json_object('```\n{"x": 1}\n```') == {"x": 1}

    def test_fenced_nested_object(self) -> None:
        # лінива `.*?` має забектрекати до закриття вкладеного об'єкта
        assert extract_json_object('```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}

    def test_raw_with_prose(self) -> None:
        assert extract_json_object('prefix {"x": 1} suffix') == {"x": 1}

    def test_raw_nested(self) -> None:
        assert extract_json_object('{"a": {"b": 1}}') == {"a": {"b": 1}}

    def test_empty_returns_none(self) -> None:
        assert extract_json_object("") is None
        assert extract_json_object("   ") is None

    def test_no_braces_returns_none(self) -> None:
        assert extract_json_object("hello world") is None

    def test_malformed_returns_none(self) -> None:
        assert extract_json_object("{bad json}") is None

    def test_non_dict_json_returns_none(self) -> None:
        # масив/число — валідний JSON, але не об'єкт → None
        assert extract_json_object("[1, 2, 3]") is None
        assert extract_json_object("42") is None


class TestKoboldToken:
    def test_data_prefix_token(self) -> None:
        assert kobold_token('data: {"token": "а"}') == "а"

    def test_without_data_prefix(self) -> None:
        assert kobold_token('{"token": "x"}') == "x"

    def test_done_sentinel(self) -> None:
        assert kobold_token("data: [DONE]") == ""
        assert kobold_token("[DONE]") == ""

    def test_empty_line(self) -> None:
        assert kobold_token("") == ""
        assert kobold_token("data:") == ""

    def test_invalid_json(self) -> None:
        assert kobold_token("data: not json") == ""

    def test_missing_token_key(self) -> None:
        assert kobold_token('data: {"foo": 1}') == ""


class TestOllamaChunk:
    def test_response_and_done(self) -> None:
        assert ollama_chunk('{"response": "x", "done": true}') == ("x", True)

    def test_response_without_done(self) -> None:
        assert ollama_chunk('{"response": "x"}') == ("x", False)

    def test_empty_line(self) -> None:
        assert ollama_chunk("") == ("", False)

    def test_invalid_json(self) -> None:
        assert ollama_chunk("not json") == ("", False)


class TestOllamaChatChunk:
    def test_content_not_done(self) -> None:
        assert ollama_chat_chunk('{"message":{"content":"hi"},"done":false}') == ("hi", False, None)

    def test_done_with_stats(self) -> None:
        delta, done, stats = ollama_chat_chunk(
            '{"message":{"content":""},"done":true,"eval_count":7,"eval_duration":1000,"model":"m"}'
        )
        assert (delta, done) == ("", True)
        assert stats == {
            "eval_count": 7, "eval_duration_ns": 1000, "prompt_eval_count": 0, "model": "m",
        }

    def test_message_not_dict(self) -> None:
        assert ollama_chat_chunk('{"message":"oops","done":false}') == ("", False, None)

    def test_invalid_and_empty(self) -> None:
        assert ollama_chat_chunk("not json") == ("", False, None)
        assert ollama_chat_chunk("") == ("", False, None)


class TestOllamaInferenceStats:
    def test_valid_stats(self) -> None:
        assert ollama_inference_stats(
            {"eval_count": 10, "eval_duration": 2000, "model": "m"}
        ) == {"eval_count": 10, "eval_duration_ns": 2000, "prompt_eval_count": 0, "model": "m"}

    def test_prompt_eval_count_passthrough(self) -> None:
        stats = ollama_inference_stats(
            {"eval_count": 10, "eval_duration": 2000, "prompt_eval_count": 33, "model": "m"}
        )
        assert stats is not None and stats["prompt_eval_count"] == 33

    def test_model_defaults_to_empty(self) -> None:
        stats = ollama_inference_stats({"eval_count": 1, "eval_duration": 1})
        assert stats is not None and stats["model"] == ""

    def test_zero_eval_count_returns_none(self) -> None:
        assert ollama_inference_stats({"eval_count": 0, "eval_duration": 2000}) is None

    def test_zero_eval_duration_returns_none(self) -> None:
        assert ollama_inference_stats({"eval_count": 10, "eval_duration": 0}) is None

    def test_non_numeric_returns_none(self) -> None:
        assert ollama_inference_stats({"eval_count": "x", "eval_duration": 2000}) is None

    def test_missing_keys_returns_none(self) -> None:
        assert ollama_inference_stats({}) is None
