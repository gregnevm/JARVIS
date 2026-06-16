"""R1 — узагальнений tool-loop engine (jarvis_core.agent.tool_loop).

Гермечно: chat/execute/coerce/inline_parser інжектовані фейками, без мережі.
Покриваємо керування петлею і контракт подій, на який спираються три варіанти
в tools/app/agent.py (sync / stream / fix).
"""
from __future__ import annotations

from typing import Any

from jarvis_core.agent.tool_loop import (
    ToolCall,
    ToolStepResult,
    assistant_message,
    extract_tool_calls,
    run_tool_loop,
)


def _coerce(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _tool_message(name: str, result: str) -> dict[str, Any]:
    return {"role": "tool", "content": f"[{name}] {result}"}


def _no_inline(_content: str) -> list[dict[str, Any]]:
    return []


class _ScriptedChat:
    """Віддає заздалегідь задані відповіді моделі по черзі."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.seen: list[int] = []

    async def __call__(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.seen.append(len(messages))
        return self._responses.pop(0)


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


# --- чисті хелпери ---
def test_assistant_message_keeps_tool_calls() -> None:
    msg = {"role": "assistant", "content": "hi", "tool_calls": [{"function": {"name": "x"}}]}
    out = assistant_message(msg)
    assert out["content"] == "hi"
    assert out["tool_calls"] == [{"function": {"name": "x"}}]


def test_assistant_message_empty_content_no_tool_calls() -> None:
    assert assistant_message({"role": "assistant"}) == {"role": "assistant", "content": ""}


def test_extract_prefers_tool_calls_over_inline() -> None:
    msg = _call("calc", {"expression": "2+2"})
    calls = extract_tool_calls(msg, _no_inline)
    assert calls == [ToolCall(name="calc", args={"expression": "2+2"})]


def test_extract_falls_back_to_inline() -> None:
    def parser(content: str) -> list[dict[str, Any]]:
        assert content == "raw"
        return [{"function": {"name": "recall", "arguments": {}}}]

    calls = extract_tool_calls({"content": "raw"}, parser)
    assert calls == [ToolCall(name="recall", args={})]


# --- петля ---
async def _drain(gen: Any) -> list[dict[str, Any]]:
    return [ev async for ev in gen]


async def test_natural_final_no_tools() -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
    chat = _ScriptedChat([{"role": "assistant", "content": "  Привіт  "}])

    async def _exec(name: str, args: Any) -> ToolStepResult:  # pragma: no cover
        raise AssertionError("execute не має викликатись без tool-calls")

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=5, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=_no_inline, tool_message=_tool_message,
        )
    )
    assert events == [{"final": "Привіт", "iters": 1}]
    assert messages[-1] == {"role": "assistant", "content": "  Привіт  "}


async def test_single_tool_then_final() -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "2+2"}]
    chat = _ScriptedChat([_call("calc", {"expression": "2+2"}), {"role": "assistant", "content": "4"}])
    coerced_seen: list[Any] = []

    async def _exec(name: str, args: Any) -> ToolStepResult:
        coerced_seen.append(args)
        return ToolStepResult(text="[calc] 4")

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=5, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=_no_inline, tool_message=_tool_message,
        )
    )
    assert {"tool_start": {"name": "calc", "args": {"expression": "2+2"}}} in events
    assert {"tool_done": {"name": "calc", "result": "[calc] 4"}} in events
    assert events[-1] == {"final": "4", "iters": 2}
    assert coerced_seen == [{"expression": "2+2"}]  # execute отримав coerced args
    assert {"role": "tool", "content": "[calc] [calc] 4"} in messages


async def test_status_emitted_when_requested() -> None:
    messages: list[dict[str, Any]] = []
    chat = _ScriptedChat([_call("web_search", {"q": "x"}), {"role": "assistant", "content": "done"}])

    async def _exec(name: str, args: Any) -> ToolStepResult:
        return ToolStepResult(text="res")

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=5, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=_no_inline, tool_message=_tool_message,
            emit_status=lambda n: {"status": f"⏳ {n}"},
        )
    )
    statuses = [e["status"] for e in events if "status" in e]
    assert statuses == ["⏳ web_search"]
    # статус іде ПЕРЕД tool_start
    assert events.index({"status": "⏳ web_search"}) < events.index(
        {"tool_start": {"name": "web_search", "args": {"q": "x"}}}
    )


async def test_need_final_when_iterations_exhausted() -> None:
    messages: list[dict[str, Any]] = []
    chat = _ScriptedChat([_call("calc", {}), _call("calc", {})])

    async def _exec(name: str, args: Any) -> ToolStepResult:
        return ToolStepResult(text="ok")

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=2, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=_no_inline, tool_message=_tool_message,
        )
    )
    assert events[-1] == {"need_final": True, "iters": 2}
    assert not any("final" in e for e in events)


async def test_confirm_event_and_done_text_split() -> None:
    """Стрім-варіант: tool_done показує pre-confirm, у messages — фінальний текст,
    а сама confirm-подія йде ПІСЛЯ tool_done."""
    messages: list[dict[str, Any]] = []
    chat = _ScriptedChat([_call("fs_write", {"path": "a"}), {"role": "assistant", "content": "ok"}])

    async def _exec(name: str, args: Any) -> ToolStepResult:
        return ToolStepResult(
            text="Очікую підтвердження",
            done_text="[[COMPUTER_CONFIRM:ab12]] ...",
            event={"confirm": {"code": "ab12"}},
        )

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=5, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=_no_inline, tool_message=_tool_message,
        )
    )
    done_idx = events.index({"tool_done": {"name": "fs_write", "result": "[[COMPUTER_CONFIRM:ab12]] ..."}})
    confirm_idx = events.index({"confirm": {"code": "ab12"}})
    assert done_idx < confirm_idx
    assert {"role": "tool", "content": "[fs_write] Очікую підтвердження"} in messages


async def test_inline_fallback_drives_loop() -> None:
    """Модель віддала виклик текстом → inline_parser підхоплює, петля виконує."""
    messages: list[dict[str, Any]] = []
    chat = _ScriptedChat([{"role": "assistant", "content": "<call>calc</call>"}, {"role": "assistant", "content": "4"}])

    def parser(content: str) -> list[dict[str, Any]]:
        if "calc" in content:
            return [{"function": {"name": "calc", "arguments": {"expression": "2+2"}}}]
        return []

    async def _exec(name: str, args: Any) -> ToolStepResult:
        return ToolStepResult(text="4")

    events = await _drain(
        run_tool_loop(
            messages=messages, limit=5, chat=chat, coerce=_coerce, execute=_exec,
            inline_parser=parser, tool_message=_tool_message,
        )
    )
    assert {"tool_start": {"name": "calc", "args": {"expression": "2+2"}}} in events
    assert events[-1] == {"final": "4", "iters": 2}
