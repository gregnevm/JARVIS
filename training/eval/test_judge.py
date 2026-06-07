"""Tests for LLM-as-judge eval helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from judge import extract_turns, judge_row, ollama_judge, parse_verdict


def test_extract_turns_sharegpt():
    row = {
        "conversations": [
            {"from": "human", "value": "Привіт"},
            {"from": "gpt", "value": "Вітаю!"},
        ]
    }
    assert extract_turns(row) == ("Привіт", "Вітаю!")


def test_extract_turns_messages():
    row = {
        "messages": [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
        ]
    }
    assert extract_turns(row) == ("Q", "A")


def test_parse_verdict():
    assert parse_verdict("PASS")[0] is True
    assert parse_verdict("FAIL: off topic")[0] is False
    assert parse_verdict("Verdict: PASS")[0] is True


def test_ollama_judge_pass():
    payload = json.dumps({"message": {"content": "PASS: helpful"}}).encode()

    class FakeResp:
        def read(self) -> bytes:
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        ok, msg = ollama_judge("hi", "hello", ollama_url="http://127.0.0.1:11434", model="m")
    assert ok is True
    assert "helpful" in msg


def test_judge_row_missing_turns():
    ok, msg = judge_row({}, ollama_url="http://x", model="m")
    assert ok is False
    assert "missing" in msg


def test_judge_row_mock():
    row = {"messages": [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]}
    with patch("judge.ollama_judge", return_value=(True, "ok")) as mock:
        ok, msg = judge_row(row, ollama_url="http://x", model="m")
    assert ok is True
    mock.assert_called_once()
