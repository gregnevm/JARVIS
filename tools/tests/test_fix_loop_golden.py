"""Golden trace CA-3.5 — live-fix-цикл (hermetic, без Ollama).

Проганяє реальний `AgentRunner._agent` зі скриптованою послідовністю tool-турів і
канонічними результатами раннерів: зламаний тест → `code_edit` → re-run → green
(і дзеркальний трейс «той самий fail двічі → чесний звіт», no-progress CA-3.4).

Скриптуємо лише траєкторію tool-call'ів моделі (як золотий запис), а сам луп,
dispatch, сигнатури fail і stop-conditions виконуються по-справжньому.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent import AgentRunner
from app.config import settings

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "fix_loop.json").read_text(encoding="utf-8")
)


class _ScriptedOllama:
    """Віддає скриптовані assistant-ходи; зберігає messages кожного chat-виклику."""

    def __init__(self, turns: list[dict[str, Any]]) -> None:
        self._responses = [self._to_response(t) for t in turns]
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _to_response(turn: dict[str, Any]) -> dict[str, Any]:
        if "final" in turn:
            return {"role": "assistant", "content": turn["final"]}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": turn["tool"], "arguments": turn.get("args", {})}}
            ],
        }

    async def chat(self, model, messages, tools=None, num_predict=1024):
        self.calls.append({"messages": [dict(m) for m in messages]})
        return self._responses.pop(0)

    async def chat_stream(self, model, messages, num_predict=1024):  # pragma: no cover
        yield ""


class _FakeMemory:
    async def search(self, user_id, query, top_k=5, project_id=None):
        return []

    async def store(self, user_id, content, role="user", project_id=None):
        return None

    async def history(self, user_id, limit=12):
        return []

    async def get_project(self, user_id, project_id):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _GOLDEN, ids=lambda c: c["id"])
async def test_fix_loop_golden(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_mode", "agent")
    monkeypatch.setattr(
        settings, "coding_no_progress_repeats", case["no_progress_repeats"]
    )

    results = iter(case["tool_results"])
    called: list[str] = []

    async def fake_dispatch(name, args, user_id, allow_computer=True):
        called.append(name)
        return next(results)

    monkeypatch.setattr("app.agent.dispatch", fake_dispatch)

    ollama = _ScriptedOllama(case["turns"])
    out = await AgentRunner(ollama, _FakeMemory()).run(1, case["user"])

    assert case["expect_final_substr"] in out["text"], out["text"]
    assert out["iters"] == case["expect_iters"]
    assert called == case["expect_tools"]

    # no-progress трейс: фінальний (форс) виклик отримав чесний stop-note.
    final_msgs = ollama.calls[-1]["messages"]
    got_stop_note = any("прогресу немає" in str(m.get("content", "")) for m in final_msgs)
    assert got_stop_note is case["expect_stop_note"]
