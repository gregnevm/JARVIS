"""Trace-хелпери AO-5: детермінізм і канонізація хешів."""
from jarvis_core.agent.trace import short_hash, tool_trace_entry


def test_short_hash_deterministic_str():
    assert short_hash("hello") == short_hash("hello")
    assert len(short_hash("hello")) == 16
    assert short_hash("hello") != short_hash("hello!")


def test_short_hash_dict_key_order_canonical():
    assert short_hash({"a": 1, "b": 2}) == short_hash({"b": 2, "a": 1})


def test_short_hash_non_serializable_falls_back_to_str():
    class X:
        def __str__(self) -> str:
            return "x-obj"

    assert short_hash(X()) == short_hash(X())


def test_short_hash_cyrillic_stable():
    assert short_hash("привіт") == short_hash("привіт")


def test_tool_trace_entry_shape():
    entry = tool_trace_entry("calc", {"expr": "2+2"}, "4")
    assert entry["tool"] == "calc"
    assert entry["args_hash"] == short_hash({"expr": "2+2"})
    assert entry["result_hash"] == short_hash("4")
    assert entry["result_len"] == 1
