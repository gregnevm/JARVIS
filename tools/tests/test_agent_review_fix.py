"""CA-5.1 — review-after-fix gate у fix_tests (self-review → авто-fix перед звітом).

Мокаємо host-agent `/cli` (run_tests + git diff) і LLM код-рев'ю; `_fix_round_edit`
застабовано. Перевіряємо: review лише за прапором, авто-fix спрацьовує на
changes_requested, skip на порожньому diff.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.agent import AgentRunner
from app.config import settings


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


_DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-return 1\n+return 2\n"
_FAIL = "FAILED tests/test_x.py::test_a\n1 failed"
_PASS = "✅ PASS\n1 passed"


class _ReviewLLM:
    """chat() повертає фіксований review-JSON (єдиний llm-виклик у gate — code_review)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = json.dumps(payload)

    async def chat(self, model, messages, tools=None):  # noqa: ANN001
        return {"content": self._payload}


def _wire(monkeypatch: pytest.MonkeyPatch, *, diff: str, edit_fixes: bool = True) -> dict:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr("app.tools.fix_loop.get_redis", lambda: _FakeRedis())

    sim = {"fixed": False}

    async def _fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        body = kwargs.get("json") or {}
        if path == "/cli" and body.get("exe") == "git":
            return {"stdout": diff, "stderr": "", "code": 0}
        # run_tests
        if sim["fixed"]:
            return {"stdout": _PASS, "stderr": "", "code": 0}
        return {"stdout": _FAIL, "stderr": "", "code": 1}

    monkeypatch.setattr("app.computer._request", _fake_request)

    async def _fake_edit_round(self, messages, tools, user_id):  # noqa: ANN001
        if edit_fixes:
            sim["fixed"] = True

    monkeypatch.setattr(AgentRunner, "_fix_round_edit", _fake_edit_round)
    return sim


async def test_review_skipped_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, diff=_DIFF)
    monkeypatch.setattr(settings, "coding_review_after_fix", False)
    runner = AgentRunner(_ReviewLLM({"verdict": "approve", "findings": []}), object())
    out = await runner.fix_tests(1, exe="pytest", review=True, max_rounds=2)
    assert out["status"] == "fixed"
    assert "review" not in out  # прапор вимкнено → жодного рев'ю


async def test_review_runs_and_autofixes(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, diff=_DIFF)
    monkeypatch.setattr(settings, "coding_review_after_fix", True)
    payload = {
        "summary": "magic number",
        "verdict": "changes_requested",
        "findings": [{"severity": "high", "file": "x.py", "line": 1, "comment": "no magic 2"}],
    }
    runner = AgentRunner(_ReviewLLM(payload), object())
    out = await runner.fix_tests(1, exe="pytest", review=True, max_rounds=2)
    assert out["status"] == "fixed"
    rv = out["review"]
    assert rv["verdict"] == "changes_requested"
    assert rv["fix_attempted"] is True
    assert rv["tests_after_fix"] == "pass"  # re-test після авто-fix лишився зелений


async def test_review_skips_on_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, diff="")
    monkeypatch.setattr(settings, "coding_review_after_fix", True)
    runner = AgentRunner(_ReviewLLM({"verdict": "approve", "findings": []}), object())
    out = await runner.fix_tests(1, exe="pytest", review=True, max_rounds=2)
    assert out["review"]["verdict"] == "skip"


async def test_review_no_autofix_when_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, diff=_DIFF)
    monkeypatch.setattr(settings, "coding_review_after_fix", True)
    runner = AgentRunner(_ReviewLLM({"summary": "lgtm", "verdict": "approve", "findings": []}), object())
    out = await runner.fix_tests(1, exe="pytest", review=True, max_rounds=2)
    assert out["review"]["verdict"] == "approve"
    assert "fix_attempted" not in out["review"]
