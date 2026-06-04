"""Агент-луп: маршрутизація CHAT/AGENT + tool-calling на AGENT-моделі.

- AGENT_MODE=chat   → завжди легка CHAT-модель, без інструментів.
- AGENT_MODE=agent  → завжди AGENT-модель з тул-лупом.
- AGENT_MODE=hybrid → евристика: математика / URL / пошукові ключі → agent, інакше chat.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from .config import settings
from .memory_client import MemoryClient
from jarvis_core.llm.chat import ChatBackend
from .toolkit import agent_tool_schemas, coerce_args, dispatch

logger = logging.getLogger("jarvis.tools.agent")

FALLBACK = "Не зміг сформувати відповідь. Спробуй переформулювати."

SYSTEM_CHAT = "Ти JARVIS — лаконічний помічник. Відповідай українською, стисло і по суті."
SYSTEM_AGENT = (
    "Ти JARVIS — помічник з інструментами. Користуйся ними, коли треба порахувати, "
    "знайти свіжу інформацію або відкрити сторінку. Не вигадуй фактів — перевіряй "
    "інструментами. Аргументи інструментів передавай мовою оригіналу (українською) — "
    "НЕ транслітеруй. Фінальну відповідь дай українською, стисло, звичайним текстом."
)

_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_MATH_RE = re.compile(r"\d\s*[-+*/^]\s*\d")
_KW_RE = re.compile(
    r"(знайд|пошук|загугл|google|search|погод|\bкурс\b|новин|обчисл|пораху|"
    r"скільки буде|calculate|відкрий\s+http|нотатк|запиши|занотуй|нагадай)",
    re.IGNORECASE,
)

# Деякі моделі (qwen2.5 в Ollama) інколи емітять tool call як текст
# <tool_call>{"name":..., "arguments":{...}}</tool_call> замість поля tool_calls.
# Ловимо такий inline-JSON як фолбек, щоб не зливати «сирий» виклик користувачу.
_INLINE_TOOL_RE = re.compile(
    r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
    re.DOTALL,
)


# Людяні статус-мітки для стріму (поки агент користується інструментом).
_TOOL_STATUS = {
    "calc": "🧮 рахую…",
    "web_search": "🔍 шукаю в інтернеті…",
    "web_fetch": "🌐 відкриваю сторінку…",
    "parse_file": "📄 читаю файл…",
    "code_exec": "⚙️ виконую код…",
    "take_note": "📝 записую нотатку…",
    "recall_notes": "📒 дивлюся нотатки…",
}


def _tool_status(name: str) -> str:
    return _TOOL_STATUS.get(name, f"🔧 {name}…")


def _parse_inline_tool_calls(content: str) -> list[dict[str, Any]]:
    """Витягує tool calls, які модель помилково віддала текстом, а не у tool_calls."""
    out: list[dict[str, Any]] = []
    for m in _INLINE_TOOL_RE.finditer(content or ""):
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            args = {}
        out.append({"function": {"name": m.group(1), "arguments": args}})
    return out


def decide_mode(text: str, agent_mode: str) -> str:
    mode = (agent_mode or "hybrid").lower()
    if mode in ("chat", "agent"):
        return mode
    t = text or ""
    if _URL_RE.search(t) or _MATH_RE.search(t) or _KW_RE.search(t):
        return "agent"
    return "chat"


def _assistant_msg(msg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


def _sys_with_ctx(base: str, ctx: str) -> str:
    return base + (f" Релевантний контекст з памʼяті: {ctx}" if ctx else "")


class AgentRunner:
    def __init__(self, llm: ChatBackend, memory: MemoryClient) -> None:
        self._llm = llm
        self._mem = memory

    async def run(
        self, user_id: int, text: str, mode: str | None = None
    ) -> dict[str, Any]:
        """Повертає {'text': ..., 'mode': 'chat'|'agent', 'iters': N}."""
        from .runtime import get_agent_mode

        results = await self._mem.search(user_id, text, top_k=5)
        ctx = " | ".join(str(r.get("content", "")) for r in results)
        resolved = mode or decide_mode(text, get_agent_mode())

        if resolved == "chat":
            answer, iters = await self._chat(text, ctx), 0
        else:
            answer, iters = await self._agent(text, ctx, user_id)

        await self._mem.store(user_id, text, role="user")
        if answer:
            await self._mem.store(user_id, answer, role="assistant")
        return {"text": answer or FALLBACK, "mode": resolved, "iters": iters}

    async def run_stream(
        self, user_id: int, text: str, mode: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу:

        - {"delta": str}  — кусок фінального тексту (додавати до відповіді),
        - {"status": str} — тимчасова мітка (агент користується інструментом),
        - {"done": True, "mode": ..., "iters": ..., "text": ...} — фінал.

        Дзеркалить run(): та сама маршрутизація, контекст і запис у памʼять.
        """
        from .runtime import get_agent_mode

        results = await self._mem.search(user_id, text, top_k=5)
        ctx = " | ".join(str(r.get("content", "")) for r in results)
        resolved = mode or decide_mode(text, get_agent_mode())

        parts: list[str] = []
        iters = 0
        if resolved == "chat":
            async for delta in self._chat_stream(text, ctx):
                parts.append(delta)
                yield {"delta": delta}
        else:
            async for ev in self._agent_events(text, ctx, user_id):
                if "iters" in ev:
                    iters = int(ev["iters"])
                    continue
                if "delta" in ev:
                    parts.append(str(ev["delta"]))
                yield ev

        answer = "".join(parts).strip()
        await self._mem.store(user_id, text, role="user")
        if answer:
            await self._mem.store(user_id, answer, role="assistant")
        yield {
            "done": True,
            "mode": resolved,
            "iters": iters,
            "text": answer or FALLBACK,
        }

    async def _chat_stream(self, text: str, ctx: str) -> AsyncIterator[str]:
        async for delta in self._llm.chat_stream(
            settings.ollama_model_chat,
            [
                {"role": "system", "content": _sys_with_ctx(SYSTEM_CHAT, ctx)},
                {"role": "user", "content": text},
            ],
        ):
            yield delta

    async def _agent_events(
        self, text: str, ctx: str, user_id: int
    ) -> AsyncIterator[dict[str, Any]]:
        """Тул-луп зі стрімом: статус на кожен виклик інструмента + фінальний текст.

        Паралельний до _agent() (не змінюємо синхронний шлях). Фінальну відповідь
        у звичайному завершенні модель уже згенерувала разом із рішенням «тулів
        більше нема» — віддаємо її одним delta; лише при вичерпанні ітерацій
        примусова відповідь без тулів стрімиться токенами.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _sys_with_ctx(SYSTEM_AGENT, ctx)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas()
        for i in range(1, settings.max_agent_iters + 1):
            msg = await self._llm.chat(settings.ollama_model_agent, messages, tools=tools)
            messages.append(_assistant_msg(msg))
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                calls = _parse_inline_tool_calls(content)
            if not calls:
                if content.strip():
                    yield {"delta": content.strip()}
                yield {"iters": i}
                return
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = coerce_args(fn.get("arguments"))
                yield {"status": _tool_status(name)}
                result = await dispatch(name, args, user_id)
                logger.info("tool[%s] -> %.80s", name, result.replace("\n", " "))
                messages.append({"role": "tool", "content": f"[{name}] {result}"})

        messages.append(
            {"role": "system", "content": "Дай фінальну відповідь користувачу без інструментів."}
        )
        async for delta in self._llm.chat_stream(settings.ollama_model_agent, messages):
            yield {"delta": delta}
        yield {"iters": settings.max_agent_iters}

    async def _chat(self, text: str, ctx: str) -> str:
        msg = await self._llm.chat(
            settings.ollama_model_chat,
            [
                {"role": "system", "content": _sys_with_ctx(SYSTEM_CHAT, ctx)},
                {"role": "user", "content": text},
            ],
        )
        return (msg.get("content") or "").strip()

    async def _agent(self, text: str, ctx: str, user_id: int) -> tuple[str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _sys_with_ctx(SYSTEM_AGENT, ctx)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas()
        for i in range(1, settings.max_agent_iters + 1):
            msg = await self._llm.chat(settings.ollama_model_agent, messages, tools=tools)
            messages.append(_assistant_msg(msg))
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                # Фолбек: модель могла віддати tool call текстом (inline XML/JSON).
                calls = _parse_inline_tool_calls(content)
            if not calls:
                return content.strip(), i
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = coerce_args(fn.get("arguments"))
                result = await dispatch(name, args, user_id)
                logger.info("tool[%s] -> %.80s", name, result.replace("\n", " "))
                messages.append({"role": "tool", "content": f"[{name}] {result}"})

        # Ітерації вичерпано — змусимо модель дати текстову відповідь без тулів.
        messages.append(
            {"role": "system", "content": "Дай фінальну відповідь користувачу без інструментів."}
        )
        final = await self._llm.chat(settings.ollama_model_agent, messages)
        return (final.get("content") or "").strip(), settings.max_agent_iters
