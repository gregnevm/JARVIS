"""Агент-луп: маршрутизація CHAT/AGENT + tool-calling на AGENT-моделі.

- AGENT_MODE=chat   → завжди легка CHAT-модель, без інструментів.
- AGENT_MODE=agent  → завжди AGENT-модель з тул-лупом.
- AGENT_MODE=hybrid → евристика: математика / URL / пошукові ключі → agent, інакше chat.
- AGENT_MODE=computer → AGENT-модель з computer-toolkit (PowerShell/CLI/FS на хості).
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from .config import settings
from .memory_client import MemoryClient
from jarvis_core.llm.chat import ChatBackend
from .toolkit import agent_tool_schemas, coerce_args, dispatch

logger = logging.getLogger("jarvis.tools.agent")

FALLBACK = "Не зміг сформувати відповідь. Спробуй переформулювати."

# Як повертати медіа (фото/файл/відео/локацію тощо) у відповіді користувачу.
MEDIA_HINT = (
    "Ти можеш повертати не лише текст, а й медіа — додай директиву наприкінці "
    "відповіді: [[photo:URL|підпис]], [[document:URL_або_шлях|підпис]], [[video:URL]], "
    "[[audio:URL]], [[animation:URL]], [[location:широта,довгота]]. Джерело — це http(s) "
    "URL, локальний шлях (/data/...) або Telegram file_id. Використовуй це, коли доречно "
    "(напр. знайдене зображення/файл за реальним URL). НЕ вигадуй неробочі посилання."
)
APP_HINT = (
    " Для багатого контенту в Mini App (Канвас) — show_in_app або директива "
    "[[app:kind|вміст]] / [[app:kind|заголовок|вміст]] (kind: html, markdown, url, image, code). "
    "html може містити <script> і CDN (Chart.js). Поряд дай короткий текстовий підсумок."
)

SYSTEM_CHAT = (
    "Ти JARVIS — лаконічний помічник. Відповідай українською, стисло і по суті. "
    + MEDIA_HINT
)
SYSTEM_AGENT = (
    "Ти JARVIS — помічник з інструментами. Користуйся ними, коли треба порахувати, "
    "знайти свіжу інформацію, відкрити сторінку, прочитати надісланий файл (parse_file) "
    "чи поставити нагадування. Не вигадуй фактів — перевіряй інструментами. Коли "
    "відповідь краще побачити, ніж прочитати (графік, таблиця, дашборд, мапа, "
    "зображення, відформатований звіт) — поклич show_in_app (Канвас Mini App) і дай "
    "поряд короткий текстовий підсумок. Для нагадування на конкретний час порахуй "
    "delay_minutes від «Зараз». Аргументи "
    "інструментів передавай мовою оригіналу (українською) — НЕ транслітеруй. Фінальну "
    "відповідь дай українською, стисло, звичайним текстом. " + MEDIA_HINT + APP_HINT
)
SYSTEM_COMPUTER = (
    "Ти JARVIS — агент керування комп'ютером Windows. Дотримуйся «драбини швидкодії»: "
    "T0 PowerShell або файлова система → T1 CLI (winget, git, curl) → T2 браузер по DOM → "
    "T3 UI Automation → T4 візуальний клік (лише останній резерв). Ніколи не обирай "
    "візуальний tier, якщо задачу можна зробити PowerShell/CLI. У відповіді коротко "
    "зазнач, яким tier ти діяв. Не вигадуй результатів — перевіряй інструментами. "
    "Фінальну відповідь дай українською, стисло. " + MEDIA_HINT
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
_CONFIRM_RE = re.compile(r"\[\[COMPUTER_CONFIRM:([a-f0-9]+)\]\]\s*(.*)", re.DOTALL)


# Людяні статус-мітки для стріму (поки агент користується інструментом).
_TOOL_STATUS = {
    "calc": "🧮 рахую…",
    "web_search": "🔍 шукаю в інтернеті…",
    "web_fetch": "🌐 відкриваю сторінку…",
    "parse_file": "📄 читаю файл…",
    "ocr_image": "🔠 розпізнаю текст на зображенні…",
    "describe_image": "👁 дивлюся на зображення…",
    "generate_image": "🎨 малюю зображення…",
    "code_exec": "⚙️ виконую код…",
    "take_note": "📝 записую нотатку…",
    "recall_notes": "📒 дивлюся нотатки…",
    "show_in_app": "🖼️ малюю у застосунку…",
    "run_powershell": "💻 PowerShell…",
    "run_cli": "⚡ CLI…",
    "fs_list": "📁 переглядаю каталог…",
    "fs_read": "📄 читаю файл…",
    "fs_write": "✍️ записую файл…",
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


def _parse_confirm(result: str) -> dict[str, str] | None:
    m = _CONFIRM_RE.match((result or "").strip())
    if not m:
        return None
    return {"code": m.group(1), "desc": m.group(2).strip()}


def decide_mode(text: str, agent_mode: str) -> str:
    mode = (agent_mode or "hybrid").lower()
    if mode in ("chat", "agent", "computer"):
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


def _agent_system(ctx: str, *, computer: bool = False) -> str:
    """Системний промпт agent/computer-режиму з поточним часом і контекстом."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    base = SYSTEM_COMPUTER if computer else SYSTEM_AGENT
    return _sys_with_ctx(f"{base} Зараз: {now}.", ctx)


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
            answer, iters = await self._agent(
                text, ctx, user_id, computer=(resolved == "computer")
            )

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
            async for ev in self._agent_events(
                text, ctx, user_id, computer=(resolved == "computer")
            ):
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
        self, text: str, ctx: str, user_id: int, *, computer: bool = False
    ) -> AsyncIterator[dict[str, Any]]:
        """Тул-луп зі стрімом: статус на кожен виклик інструмента + фінальний текст.

        Паралельний до _agent() (не змінюємо синхронний шлях). Фінальну відповідь
        у звичайному завершенні модель уже згенерувала разом із рішенням «тулів
        більше нема» — віддаємо її одним delta; лише при вичерпанні ітерацій
        примусова відповідь без тулів стрімиться токенами.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer)
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
                confirm = _parse_confirm(result)
                if confirm:
                    yield {"confirm": confirm}
                    result = (
                        f"Очікую підтвердження в Telegram (код {confirm['code']}): "
                        f"{confirm['desc']}"
                    )
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

    async def _agent(
        self, text: str, ctx: str, user_id: int, *, computer: bool = False
    ) -> tuple[str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer)
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
                confirm = _parse_confirm(result)
                if confirm:
                    # Синхронний шлях: повідомлення моделі про pending; gateway шле кнопки окремо.
                    result = (
                        f"[[COMPUTER_CONFIRM:{confirm['code']}]] "
                        f"Очікую підтвердження: {confirm['desc']}"
                    )
                logger.info("tool[%s] -> %.80s", name, result.replace("\n", " "))
                messages.append({"role": "tool", "content": f"[{name}] {result}"})

        # Ітерації вичерпано — змусимо модель дати текстову відповідь без тулів.
        messages.append(
            {"role": "system", "content": "Дай фінальну відповідь користувачу без інструментів."}
        )
        final = await self._llm.chat(settings.ollama_model_agent, messages)
        return (final.get("content") or "").strip(), settings.max_agent_iters
