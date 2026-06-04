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
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from .config import settings
from .memory_client import MemoryClient
from .thread_context import build_thread_context
from .user_profile import profile_prompt_block
from jarvis_core.llm.chat import ChatBackend
from .toolkit import agent_tool_schemas, coerce_args, dispatch, image_gen_enabled

logger = logging.getLogger("jarvis.tools.agent")

FALLBACK = "Не зміг сформувати відповідь. Спробуй переформулювати."

def media_hint() -> str:
    """Підказка для [[photo:…]] з урахуванням увімкненої генерації зображень."""
    base = (
        "Ти можеш повертати не лише текст, а й медіа — додай директиву наприкінці "
        "відповіді: [[photo:URL|підпис]], [[document:URL_або_шлях|підпис]], [[video:URL]], "
        "[[audio:URL]], [[animation:URL]], [[location:широта,довгота]]. Джерело — лише "
        "http(s) URL, існуючий шлях /data/uploads/... з інструмента або Telegram file_id. "
        "НЕ вигадуй імена файлів (puppy.jpg тощо)."
    )
    if image_gen_enabled():
        return (
            base
            + " Для картинки за описом — спочатку generate_image; у [[photo:]] лише шлях "
            "з відповіді інструмента або реальний URL."
        )
    return (
        base
        + " Генерація зображень вимкнена — не обіцяй картинку; локально: Forge "
        "(scripts/start_sd_forge.ps1, IMAGE_GEN_URL=:7860)."
    )


APP_HINT = (
    " Для багатого контенту в Mini App (Канвас) — show_in_app або директива "
    "[[app:kind|вміст]] / [[app:kind|заголовок|вміст]] (kind: html, markdown, url, image, code). "
    "html може містити <script> і CDN (Chart.js). Поряд дай короткий текстовий підсумок."
)

def system_chat() -> str:
    return (
        "Ти JARVIS — лаконічний помічник. Відповідай українською, стисло і по суті. "
        + media_hint()
    )


def system_agent() -> str:
    return (
        "Ти JARVIS — помічник з інструментами. Користуйся ними, коли треба порахувати, "
        "знайти свіжу інформацію, відкрити сторінку, прочитати надісланий файл (parse_file), "
        "згенерувати зображення (generate_image, якщо доступно), "
        "зняти скріншот екрана (capture_screenshot, якщо увімкнено Computer Use) "
        "чи поставити нагадування. Команда /app — Mini App дашборд, не шлях у ФС. "
        "Не вигадуй фактів — перевіряй інструментами. Коли "
        "відповідь краще побачити, ніж прочитати (графік, таблиця, дашборд, мапа, "
        "зображення, відформатований звіт) — поклич show_in_app (Канвас Mini App) і дай "
        "поряд короткий текстовий підсумок. Для нагадування на конкретний час порахуй "
        "delay_minutes від «Зараз». Аргументи "
        "інструментів передавай мовою оригіналу (українською) — НЕ транслітеруй. Фінальну "
        "відповідь дай українською, стисло, звичайним текстом. " + media_hint() + APP_HINT
    )


def system_computer() -> str:
    vision = ""
    if settings.ollama_model_vision:
        vision = (
            " Для «що на екрані?» — спочатку capture_screenshot, потім describe_image "
            "з шляхом з відповіді та питанням користувача."
        )
    return (
        "Ти JARVIS — агент керування комп'ютером Windows. Дотримуйся «драбини швидкодії»: "
        "T0 PowerShell (whitelist) і fs_* — найперший вибір для OS/файлів; T1 CLI (whitelist) — "
        "для git, winget, curl тощо; capture_screenshot — зняти екран. "
        "Браузер (Playwright), UI Automation і піксельний клік НЕ доступні — не вигадуй їх. "
        "Команда /app — Mini App дашборд, не шлях у ФС. "
        "Не вигадуй результатів — перевіряй інструментами. "
        "У фінальній відповіді коротко вкажи tier (T0/T1), яким діяв."
        + vision
        + " Фінальну відповідь українською, стисло. "
        + media_hint()
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
    "capture_screenshot": "📸 знімаю екран…",
    "browser_open": "🌐 браузер…",
    "browser_read": "🌐 читаю сторінку…",
    "browser_click": "🌐 клік…",
    "browser_fill": "🌐 форма…",
    "browser_eval": "🌐 JS…",
    "window_list": "🪟 вікна…",
    "window_focus": "🪟 фокус…",
    "uia_invoke": "🪟 UIA…",
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


def _resolve_mode_hint(hint: str | None) -> str | None:
    """Явний mode з gateway (computer_resume тощо) — не перезаписуємо евристикою."""
    h = (hint or "").lower().strip()
    if h in ("chat", "agent", "computer"):
        return h
    return None


def decide_mode(
    text: str,
    agent_mode: str,
    *,
    mode_hint: str | None = None,
    user_id: int = 0,
) -> str:
    from jarvis_core.routing import RouteContext, classify_mode

    from .computer_access import can_use_computer

    return classify_mode(
        text,
        RouteContext(
            agent_mode=agent_mode,
            mode_hint=_resolve_mode_hint(mode_hint),
            user_id=user_id,
            enable_computer=settings.enable_computer_use,
            computer_allowed=can_use_computer(user_id),
        ),
    )


def _max_iters(*, computer: bool = False) -> int:
    if computer:
        return max(settings.computer_max_iters, settings.max_agent_iters)
    return settings.max_agent_iters


def _assistant_msg(msg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


def _sys_with_ctx(base: str, ctx: str) -> str:
    return base + (f" Релевантний контекст з памʼяті: {ctx}" if ctx else "")


def _agent_system(ctx: str, *, computer: bool = False, profile: str = "") -> str:
    """Системний промпт agent/computer-режиму з поточним часом і контекстом."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    base = system_computer() if computer else system_agent()
    return _sys_with_ctx(f"{base} Зараз: {now}.{profile}", ctx)


class AgentRunner:
    def __init__(self, llm: ChatBackend, memory: MemoryClient) -> None:
        self._llm = llm
        self._mem = memory

    async def _persist_turn(
        self, user_id: int, text: str, answer: str, mode: str, iters: int
    ) -> None:
        await self._mem.store(user_id, text, role="user")
        if answer:
            await self._mem.store(user_id, answer, role="assistant")
        from .session_ingest import append_turn

        append_turn(
            user_id,
            user_text=text,
            assistant_text=answer,
            mode=mode,
            iters=iters,
        )

    async def _memory_context(self, user_id: int, text: str) -> tuple[str, str]:
        from .metrics import record_rag

        results = await self._mem.search(user_id, text, top_k=5)
        await record_rag(len(results))
        rag = " | ".join(str(r.get("content", "")) for r in results)
        thread = await build_thread_context(self._mem, user_id)
        prof = profile_prompt_block(user_id)
        parts = [p for p in (rag, thread) if p]
        return (" | ".join(parts) if parts else ""), prof

    async def run(
        self, user_id: int, text: str, mode: str | None = None, *, mode_hint: str | None = None
    ) -> dict[str, Any]:
        """Повертає {'text': ..., 'mode': 'chat'|'agent'|'computer', 'iters': N}."""
        from .runtime import get_agent_mode

        from .metrics import record_turn

        t0 = time.perf_counter()
        iters = 0
        resolved = "chat"
        ctx, prof = await self._memory_context(user_id, text)
        hint = mode_hint or mode
        resolved = _resolve_mode_hint(hint) or decide_mode(
            text, get_agent_mode(), mode_hint=hint, user_id=user_id
        )

        try:
            if resolved == "chat":
                answer, iters = await self._chat(text, ctx, prof), 0
            else:
                from .computer_access import can_use_computer

                answer, iters = await self._agent(
                    text,
                    ctx,
                    user_id,
                    computer=(resolved == "computer"),
                    allow_computer=can_use_computer(user_id),
                    profile=prof,
                )

            await self._persist_turn(user_id, text, answer or "", resolved, iters)
            return {"text": answer or FALLBACK, "mode": resolved, "iters": iters}
        finally:
            await record_turn((time.perf_counter() - t0) * 1000, resolved, iters)

    async def run_stream(
        self, user_id: int, text: str, mode: str | None = None, *, mode_hint: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу:

        - {"delta": str}  — кусок фінального тексту (додавати до відповіді),
        - {"status": str} — тимчасова мітка (агент користується інструментом),
        - {"done": True, "mode": ..., "iters": ..., "text": ...} — фінал.

        Дзеркалить run(): та сама маршрутизація, контекст і запис у памʼять.
        """
        from .runtime import get_agent_mode

        from .metrics import record_turn

        t0 = time.perf_counter()
        iters = 0
        resolved = "chat"
        ctx, prof = await self._memory_context(user_id, text)
        hint = mode_hint or mode
        resolved = _resolve_mode_hint(hint) or decide_mode(
            text, get_agent_mode(), mode_hint=hint, user_id=user_id
        )

        parts: list[str] = []
        try:
            if resolved == "chat":
                async for delta in self._chat_stream(text, ctx, prof):
                    parts.append(delta)
                    yield {"delta": delta}
            else:
                from .computer_access import can_use_computer

                async for ev in self._agent_events(
                    text,
                    ctx,
                    user_id,
                    computer=(resolved == "computer"),
                    allow_computer=can_use_computer(user_id),
                    profile=prof,
                ):
                    if "iters" in ev:
                        iters = int(ev["iters"])
                        continue
                    if "delta" in ev:
                        parts.append(str(ev["delta"]))
                    yield ev

            answer = "".join(parts).strip()
            await self._persist_turn(user_id, text, answer or "", resolved, iters)
            yield {
                "done": True,
                "mode": resolved,
                "iters": iters,
                "text": answer or FALLBACK,
            }
        finally:
            await record_turn((time.perf_counter() - t0) * 1000, resolved, iters)

    async def _chat_stream(self, text: str, ctx: str, profile: str = "") -> AsyncIterator[str]:
        async for delta in self._llm.chat_stream(
            settings.ollama_model_chat,
            [
                {"role": "system", "content": _sys_with_ctx(system_chat() + profile, ctx)},
                {"role": "user", "content": text},
            ],
        ):
            yield delta

    async def _agent_events(
        self,
        text: str,
        ctx: str,
        user_id: int,
        *,
        computer: bool = False,
        allow_computer: bool = True,
        profile: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """Тул-луп зі стрімом: статус на кожен виклик інструмента + фінальний текст.

        Паралельний до _agent() (не змінюємо синхронний шлях). Фінальну відповідь
        у звичайному завершенні модель уже згенерувала разом із рішенням «тулів
        більше нема» — віддаємо її одним delta; лише при вичерпанні ітерацій
        примусова відповідь без тулів стрімиться токенами.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer, profile=profile)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer, allow_computer=allow_computer)
        limit = _max_iters(computer=computer)
        for i in range(1, limit + 1):
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
                result = await dispatch(name, args, user_id, allow_computer=allow_computer)
                confirm = _parse_confirm(result)
                if confirm:
                    from .computer_confirm import save_origin

                    await save_origin(user_id, text)
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
        yield {"iters": limit}

    async def _chat(self, text: str, ctx: str, profile: str = "") -> str:
        msg = await self._llm.chat(
            settings.ollama_model_chat,
            [
                {"role": "system", "content": _sys_with_ctx(system_chat() + profile, ctx)},
                {"role": "user", "content": text},
            ],
        )
        return (msg.get("content") or "").strip()

    async def _agent(
        self,
        text: str,
        ctx: str,
        user_id: int,
        *,
        computer: bool = False,
        allow_computer: bool = True,
        profile: str = "",
    ) -> tuple[str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer, profile=profile)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer, allow_computer=allow_computer)
        limit = _max_iters(computer=computer)
        for i in range(1, limit + 1):
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
                result = await dispatch(name, args, user_id, allow_computer=allow_computer)
                confirm = _parse_confirm(result)
                if confirm:
                    from .computer_confirm import save_origin

                    await save_origin(user_id, text)
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
        return (final.get("content") or "").strip(), limit
