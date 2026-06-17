"""Tool-loop engine — єдина петля «модель → tool-calls → виконання → результат».

До R1 ця петля існувала у трьох дослівних копіях у `tools/app/agent.py`
(`_agent` синхронний, `_agent_events` стрім, `_fix_round_edit` fix-раунд), що
давало клас багів розсинхрону. Тут вона одна, а три варіанти — тонкі споживачі.

Engine навмисно **не знає** про `dispatch`, hooks, confirm чи статус-мітки — усе
це інжектується. Він володіє ЛИШЕ керуванням петлею:

    for i in 1..limit:
        msg   = await chat(messages)            # крок моделі
        append assistant(msg)
        calls = extract_tool_calls(msg)         # tool_calls або inline-фолбек
        if not calls: -> подія {"final": <текст>, "iters": i}; стоп
        for call in calls:
            coerced = coerce(call.args)
            -> {"status": ...}  (опційно)
            -> {"tool_start": {name, args=coerced}}
            res = await execute(name, coerced)  # dispatch + hooks + confirm
            -> {"tool_done": {name, result}}
            -> res.event  (опційно, напр. confirm)
            append tool_message(name, res.text)
    -> подія {"need_final": True, "iters": limit}   # ітерації вичерпано

Споживач сам вирішує, що робити на `final` (повернути/стрімити) і на
`need_final` (примусова відповідь без тулів через chat або chat_stream) —
саме так зберігаються відмінності sync vs stream без дублювання петлі.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

MessageDict = dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """Один виклик інструмента, видобутий з відповіді моделі. `args` — сирі."""

    name: str
    args: Any


@dataclass(frozen=True)
class ToolStepResult:
    """Результат виконання одного інструмента (повертає інжектований `execute`).

    - `text` — те, що дописується у messages як вміст tool-повідомлення
      (для confirm — уже відрендерений фінальний текст);
    - `done_text` — те, що показати у події `tool_done` (для confirm це
      pre-confirm результат; None → дорівнює `text`);
    - `event` — необовʼязкова додаткова подія для споживача (напр. `{"confirm": ...}`).
    """

    text: str
    done_text: str | None = None
    event: dict[str, Any] | None = None


# Інжектовані залежності (усе сервіс-специфічне живе тут, не в engine):
ChatFn = Callable[[list[MessageDict]], Awaitable[MessageDict]]
CoerceFn = Callable[[Any], Any]
ExecuteFn = Callable[[str, Any], Awaitable[ToolStepResult]]
InlineParser = Callable[[str], list[MessageDict]]
ToolMessageFn = Callable[[str, str], MessageDict]
StatusFn = Callable[[str], dict[str, Any]]


def assistant_message(msg: MessageDict) -> MessageDict:
    """Нормалізує відповідь моделі у assistant-повідомлення для історії."""
    out: MessageDict = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


def extract_tool_calls(msg: MessageDict, inline_parser: InlineParser) -> list[ToolCall]:
    """tool_calls з відповіді або inline-фолбек, якщо модель віддала виклик текстом."""
    raw = msg.get("tool_calls") or []
    if not raw:
        raw = inline_parser(msg.get("content") or "")
    calls: list[ToolCall] = []
    for call in raw:
        fn = call.get("function") or {}
        calls.append(ToolCall(name=str(fn.get("name", "")), args=fn.get("arguments")))
    return calls


async def run_tool_loop(
    *,
    messages: list[MessageDict],
    limit: int,
    chat: ChatFn,
    coerce: CoerceFn,
    execute: ExecuteFn,
    inline_parser: InlineParser,
    tool_message: ToolMessageFn,
    emit_status: StatusFn | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Ганяє tool-loop, мутуючи `messages`, і ʼїлдить події (див. docstring модуля)."""
    for i in range(1, limit + 1):
        msg = await chat(messages)
        messages.append(assistant_message(msg))
        calls = extract_tool_calls(msg, inline_parser)
        if not calls:
            yield {"final": (msg.get("content") or "").strip(), "iters": i}
            return
        for call in calls:
            args = coerce(call.args)
            if emit_status is not None:
                yield emit_status(call.name)
            yield {"tool_start": {"name": call.name, "args": args}}
            res = await execute(call.name, args)
            yield {
                "tool_done": {
                    "name": call.name,
                    "result": res.done_text if res.done_text is not None else res.text,
                }
            }
            if res.event is not None:
                yield res.event
            messages.append(tool_message(call.name, res.text))
    yield {"need_final": True, "iters": limit}
