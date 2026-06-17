"""CA-3.2 — виділена fix-orchestration (AgentRunner.fix_tests).

Гермечно: LLM і run_tests замокані; перевіряємо керування петлею та стоп-умови
(already_green / fixed / no_progress / stuck) і що раунд реально диспатчить code_edit.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent import AgentRunner

_FAIL_A = (
    "pytest ❌ FAIL — passed=3 failed=1 errors=0 skipped=0 (exit 1)\n"
    "failed:\n  tests/test_a.py::test_one\n---\ntail"
)
_FAIL_B = (
    "pytest ❌ FAIL — passed=3 failed=1 errors=0 skipped=0 (exit 1)\n"
    "failed:\n  tests/test_b.py::test_two\n---\ntail"
)
_FAIL_C = (
    "pytest ❌ FAIL — passed=3 failed=1 errors=0 skipped=0 (exit 1)\n"
    "failed:\n  tests/test_c.py::test_three\n---\ntail"
)
_PASS = "pytest ✅ PASS — passed=4 failed=0 errors=0 skipped=0 (exit 0)\n---\nok"


class ScriptedLLM:
    """Віддає заскриптовані відповіді; вичерпавши — повертає no-tool message."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls = 0

    async def chat(self, model: str, messages: list[dict], tools: Any = None) -> dict[str, Any]:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {"content": "готово"}


def _patch_run_tests(monkeypatch: pytest.MonkeyPatch, verdicts: list[str]) -> None:
    queue = list(verdicts)

    async def _rt(exe: str, *, args: Any = None, path: str = "", user_id: int = 0,
                  framework: str = "auto") -> str:
        return queue.pop(0) if queue else verdicts[-1]

    monkeypatch.setattr("app.tools.check_tools.run_tests", _rt)
    # схеми тулів не потрібні (LLM замокана) — тримаємо порожніми для гермечності
    monkeypatch.setattr("app.agent.agent_tool_schemas", lambda **_: [])


def _runner(llm: ScriptedLLM) -> AgentRunner:
    return AgentRunner(llm, object())


async def test_fix_tests_already_green(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_tests(monkeypatch, [_PASS])
    llm = ScriptedLLM()
    out = await _runner(llm).fix_tests(1, exe="pytest")
    assert out["status"] == "already_green" and out["rounds"] == 0
    assert llm.calls == 0  # зелено на старті — модель не чіпаємо


async def test_fix_tests_fixed_after_one_round(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_tests(monkeypatch, [_FAIL_A, _PASS])
    out = await _runner(ScriptedLLM()).fix_tests(1, exe="pytest", max_rounds=3)
    assert out["status"] == "fixed" and out["rounds"] == 1
    assert "✅ PASS" in out["report"]


async def test_fix_tests_no_progress_same_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    # той самий набір впалих тестів після раунду → стоп no_progress
    _patch_run_tests(monkeypatch, [_FAIL_A, _FAIL_A])
    out = await _runner(ScriptedLLM()).fix_tests(1, exe="pytest", max_rounds=4)
    assert out["status"] == "no_progress" and out["rounds"] == 1


async def test_fix_tests_stuck_after_max_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    # щоразу інший fail (є «прогрес») → вичерпуємо ліміт раундів
    _patch_run_tests(monkeypatch, [_FAIL_A, _FAIL_B, _FAIL_C])
    out = await _runner(ScriptedLLM()).fix_tests(1, exe="pytest", max_rounds=2)
    assert out["status"] == "stuck" and out["rounds"] == 2


async def test_fix_round_dispatches_code_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_tests(monkeypatch, [_FAIL_A, _PASS])
    disp = AsyncMock(return_value="[code_edit] ok")
    monkeypatch.setattr("app.agent.dispatch", disp)
    llm = ScriptedLLM(
        [
            {"tool_calls": [{"function": {"name": "code_edit",
                                          "arguments": {"path": "x.py", "old_string": "a",
                                                        "new_string": "b"}}}]},
            {"content": "правку внесено"},  # без тулів → раунд завершується
        ]
    )
    out = await _runner(llm).fix_tests(1, exe="pytest", max_rounds=2)
    assert out["status"] == "fixed" and out["rounds"] == 1
    assert disp.await_count == 1
    assert disp.await_args.args[0] == "code_edit"


async def test_fix_tests_no_review_when_no_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    # Green без правок (already-fixed після раунду без code_edit) → без review-блоку.
    _patch_run_tests(monkeypatch, [_FAIL_A, _PASS])
    out = await _runner(ScriptedLLM()).fix_tests(1, exe="pytest", max_rounds=2)
    assert out["status"] == "fixed" and "review" not in out
