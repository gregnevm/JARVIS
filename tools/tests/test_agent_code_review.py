"""CA-5.1 — self-review pass (AgentRunner.code_review). Mock LLM JSON."""
from __future__ import annotations

import json

import pytest

from app.agent import AgentRunner


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, model, messages, tools=None):  # noqa: ANN001
        return {"content": self.content}


_DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-return 1\n+return 2\n"


async def test_code_review_empty_diff_skips() -> None:
    out = await AgentRunner(FakeLLM("{}"), object()).code_review(1, diff="")
    assert out["verdict"] == "skip" and out["findings"] == []


async def test_code_review_parses_findings() -> None:
    payload = {
        "summary": "off-by-one risk",
        "verdict": "changes_requested",
        "findings": [
            {"severity": "high", "file": "x.py", "line": 2, "comment": "magic number"},
            {"severity": "weird", "file": "x.py", "line": "bad", "comment": "style"},
        ],
    }
    out = await AgentRunner(FakeLLM(json.dumps(payload)), object()).code_review(1, diff=_DIFF)
    assert out["verdict"] == "changes_requested"
    assert len(out["findings"]) == 2
    assert out["findings"][0]["severity"] == "high" and out["findings"][0]["line"] == 2
    # невалідні поля нормалізуються
    assert out["findings"][1]["severity"] == "medium" and out["findings"][1]["line"] == 0


async def test_code_review_verdict_defaults_to_approve_when_no_findings() -> None:
    out = await AgentRunner(FakeLLM('{"summary":"lgtm","findings":[]}'), object()).code_review(
        1, diff=_DIFF
    )
    assert out["verdict"] == "approve" and out["findings"] == []


async def test_code_review_handles_non_json() -> None:
    out = await AgentRunner(FakeLLM("not json at all"), object()).code_review(1, diff=_DIFF)
    # graceful: без findings → approve, summary з контенту
    assert out["verdict"] == "approve"
    assert "not json" in out["summary"]
