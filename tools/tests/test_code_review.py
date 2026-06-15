"""CA-5.1 code_review self-pass — structured findings + verdict (mock LLM)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app import agent as agent_mod
from app.agent import AgentRunner, _normalize_findings


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[Any] = []

    async def chat(self, model, messages, tools=None):  # noqa: ANN001
        self.calls.append(messages)
        return {"content": self.content}


# --- _normalize_findings -----------------------------------------------------

def test_normalize_findings_filters_and_clamps_severity():
    out = _normalize_findings([
        {"file": "a.py", "severity": "CRITICAL", "note": "bug"},  # невідома → medium
        {"file": "b.py", "severity": "low", "note": "nit"},
        {"severity": "high"},  # без note → відкидається
        "не dict",
    ])
    assert len(out) == 2
    assert out[0] == {"file": "a.py", "severity": "medium", "note": "bug"}
    assert out[1]["severity"] == "low"


def test_normalize_findings_non_list():
    assert _normalize_findings(None) == []


# --- code_review -------------------------------------------------------------

async def test_code_review_clean_when_no_findings():
    llm = FakeLLM(json.dumps({"summary": "ok", "findings": []}))
    out = await AgentRunner(llm, object()).code_review(1, diff="diff --git a b\n+x")
    assert out["verdict"] == "clean" and out["findings"] == []


async def test_code_review_issues_when_medium_or_high():
    payload = {"summary": "є баг", "findings": [{"file": "x.py", "severity": "high", "note": "NPE"}]}
    llm = FakeLLM(json.dumps(payload))
    out = await AgentRunner(llm, object()).code_review(1, diff="some diff")
    assert out["verdict"] == "issues"
    assert out["findings"][0]["severity"] == "high"


async def test_code_review_low_only_is_clean():
    payload = {"summary": "дрібниці", "findings": [{"file": "x.py", "severity": "low", "note": "nit"}]}
    out = await AgentRunner(FakeLLM(json.dumps(payload)), object()).code_review(1, diff="d")
    assert out["verdict"] == "clean"  # лише low → не блокер


async def test_code_review_empty_diff_short_circuits():
    llm = FakeLLM("не має викликатись")
    out = await AgentRunner(llm, object()).code_review(1, diff="   ")
    assert out["verdict"] == "empty"
    assert llm.calls == []  # LLM не чіпаємо без diff


async def test_code_review_fetches_git_diff_from_path(monkeypatch: pytest.MonkeyPatch):
    async def _fake_request(method, path, **kwargs):  # noqa: ANN001
        assert path == "/cli"
        assert kwargs["json"]["args"][:4] == ["-C", "/repo", "--no-pager", "diff"]
        return {"stdout": "diff --git a b\n-old\n+new", "code": 0}

    monkeypatch.setattr("app.computer._request", _fake_request)
    llm = FakeLLM(json.dumps({"summary": "ok", "findings": []}))
    out = await AgentRunner(llm, object()).code_review(1, path="/repo")
    assert out["verdict"] == "clean"
    assert llm.calls  # diff знайдено → рев'ю відбувся


async def test_code_review_bad_json_degrades_gracefully():
    out = await AgentRunner(FakeLLM("геть не JSON"), object()).code_review(1, diff="d")
    assert out["verdict"] == "clean" and out["findings"] == []
