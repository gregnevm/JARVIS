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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .tools.check_tools import ProgressGuard

from .config import settings
from .memory_client import MemoryClient
from .thread_context import build_thread_context
from .user_profile import profile_prompt_block
from jarvis_core.llm.chat import ChatBackend
from jarvis_core.llm.parsers import extract_json_object
from .toolkit import agent_tool_schemas, coerce_args, dispatch, image_gen_enabled

logger = logging.getLogger("jarvis.tools.agent")

FALLBACK = "Не зміг сформувати відповідь. Спробуй переформулювати."

PLAN_MARKER = "[[PLAN_CONFIRM:{id}]]"
_PLAN_MAX_STEPS = 8
_TOOL_MEDIA_RE = re.compile(
    r"\[\[\s*(?:photo|image|document|file)\s*:\s*[^\]]+\]\]",
    re.IGNORECASE,
)


def _collect_tool_media(messages: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        for directive in _TOOL_MEDIA_RE.findall(str(m.get("content") or "")):
            if directive not in seen:
                seen.add(directive)
                out.append(directive)
    return out


def _ensure_tool_media(answer: str, messages: list[dict[str, Any]]) -> str:
    """Додає [[photo:…]] з результатів інструментів, якщо модель їх пропустила."""
    directives = _collect_tool_media(messages)
    if not directives:
        return answer
    answer = (answer or "").strip()
    missing = [d for d in directives if d not in answer]
    if not missing:
        return answer
    return answer + "\n\n" + "\n".join(missing)


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
    from .computer_profile import format_tools_prompt_block

    tools_block = format_tools_prompt_block(computer=True)
    vision_hint = ""
    if settings.ollama_model_vision:
        if "see_screen" in tools_block:
            vision_hint = (
                " Для «що на екрані?» — see_screen(question=…); "
                "або capture_screenshot + describe_image."
            )
        else:
            vision_hint = (
                " Для «що на екрані?» — capture_screenshot, потім describe_image."
            )
    return (
        "Ти JARVIS — агент керування комп'ютером Windows. Дотримуйся «драбини швидкодії» "
        "(T0→T1→T2→T3→T4): спочатку PowerShell/CLI/FS, потім браузер по DOM, потім UIA, "
        "і лише в крайньому випадку піксельний клік. "
        f"{tools_block} "
        "Використовуй ЛИШЕ інструменти зі списку — не вигадуй інших. "
        "Якщо користувач пише cursor: … — одразу cursor_task(async_mode=true), не run_powershell. "
        "PowerShell: без пайпів |, &&, ||, $( ) — лише прості cmdlet з PS_WHITELIST; "
        "список процесів — Get-Process або Get-Process -Name ollama,python. "
        "CLI fallback: run_cli python + O:\\JARVIS\\scripts\\cursor_run_task.py. "
        "Команда /app — Mini App дашборд, не шлях у ФС. "
        "Не вигадуй результатів — перевіряй інструментами. "
        "У фінальній відповіді коротко вкажи tier, яким діяв."
        + vision_hint
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
    "code_edit": "🩹 редагую код (diff)…",
    "code_edit_batch": "🩹 правки кількох файлів (транзакційно)…",
    "rename_symbol": "✏️ перейменування по репо…",
    "repo_tree": "🌳 дерево репо…",
    "repo_grep": "🔎 шукаю в коді…",
    "code_read": "📄 читаю рядки…",
    "repo_symbols": "🧭 символи файлу…",
    "run_tests": "🧪 ганяю тести…",
    "run_lint": "🔬 лінт/типи…",
    "capture_screenshot": "📸 знімаю екран…",
    "see_screen": "👁 дивлюся на екран…",
    "browser_open": "🌐 браузер…",
    "browser_read": "🌐 читаю сторінку…",
    "browser_click": "🌐 клік…",
    "browser_fill": "🌐 форма…",
    "browser_eval": "🌐 JS…",
    "window_list": "🪟 вікна…",
    "window_focus": "🪟 фокус…",
    "uia_invoke": "🪟 UIA…",
    "screen_click": "🖱 клік…",
    "screen_type": "⌨️ ввід…",
    "screen_hotkey": "⌨️ hotkey…",
    "screen_scroll": "🖱 scroll…",
    "cursor_task": "🧠 Cursor IDE…",
    "spawn_subagent": "🤖 subagent…",
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


def _max_iters(*, computer: bool = False, override: int | None = None) -> int:
    if override is not None:
        return max(1, min(int(override), settings.computer_max_iters if computer else settings.max_agent_iters))
    if computer:
        return max(settings.computer_max_iters, settings.max_agent_iters)
    return settings.max_agent_iters


_STOP_NO_PROGRESS = (
    "Тести/лінт двічі поспіль впали з тим самим результатом — прогресу немає. "
    "Зупини fix-цикл і чесно звітуй користувачу: що саме падає, що ти вже пробував "
    "і чому застряг. Без подальших інструментів."
)
_STOP_MAX_ITERS = "Дай фінальну відповідь користувачу без інструментів."


def _stop_note(*, no_progress: bool) -> str:
    return _STOP_NO_PROGRESS if no_progress else _STOP_MAX_ITERS


_SEVERITIES = frozenset({"low", "medium", "high"})


def _normalize_findings(raw: Any) -> list[dict[str, str]]:
    """Code-review findings → [{file, severity, note}] (CA-5.1)."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for f in raw[:50]:
        if not isinstance(f, dict):
            continue
        note = str(f.get("note") or f.get("message") or "").strip()
        if not note:
            continue
        sev = str(f.get("severity") or "medium").strip().lower()
        out.append({
            "file": str(f.get("file") or "")[:300],
            "severity": sev if sev in _SEVERITIES else "medium",
            "note": note[:1000],
        })
    return out


def _progress_guard() -> "ProgressGuard":
    from .tools.check_tools import ProgressGuard

    return ProgressGuard(settings.coding_no_progress_repeats)


def _observe_check(guard: "ProgressGuard", name: str, result: str) -> bool:
    """True, якщо check-tool (run_tests/run_lint) дав той самий fail N разів поспіль."""
    from .tools.check_tools import CHECK_TOOLS, failure_signature

    if name not in CHECK_TOOLS:
        return False
    return guard.observe(failure_signature(result))


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
        self,
        user_id: int,
        text: str,
        answer: str,
        mode: str,
        iters: int,
        project_id: int | None = None,
    ) -> None:
        await self._mem.store(user_id, text, role="user", project_id=project_id)
        if answer:
            await self._mem.store(user_id, answer, role="assistant", project_id=project_id)
        from .session_ingest import append_turn

        append_turn(
            user_id,
            user_text=text,
            assistant_text=answer,
            mode=mode,
            iters=iters,
        )

    async def _resolve_project(self, user_id: int) -> tuple[int | None, str]:
        """Активний проєкт користувача → (project_id, system-блок). Видалений/чужий
        проєкт скидаємо (fail-safe на загальний контекст)."""
        from .projects import active_project_id, project_prompt_block, set_active_project

        pid = await active_project_id(user_id)
        if pid is None:
            return None, ""
        proj = await self._mem.get_project(user_id, pid, include_content=True)
        if not proj:
            await set_active_project(user_id, None)
            return None, ""
        return pid, project_prompt_block(proj)

    async def _memory_context(
        self, user_id: int, text: str, project_id: int | None = None
    ) -> tuple[str, str]:
        from .metrics import record_rag

        results = await self._mem.search(user_id, text, top_k=5, project_id=project_id)
        await record_rag(len(results))
        rag = " | ".join(str(r.get("content", "")) for r in results)
        thread = await build_thread_context(self._mem, user_id)
        prof = profile_prompt_block(user_id)
        parts = [p for p in (rag, thread) if p]
        return (" | ".join(parts) if parts else ""), prof

    async def run(
        self,
        user_id: int,
        text: str,
        mode: str | None = None,
        *,
        mode_hint: str | None = None,
        max_iters_override: int | None = None,
    ) -> dict[str, Any]:
        """Повертає {'text': ..., 'mode': 'chat'|'agent'|'computer', 'iters': N}."""
        from .runtime import get_agent_mode
        from . import hooks as agent_hooks

        from .metrics import record_turn

        t0 = time.perf_counter()
        iters = 0
        resolved = "chat"
        hook_ctx = await agent_hooks.run_pre_turn(
            {"user_id": user_id, "text": text, "mode": mode or ""}
        )
        text = str(hook_ctx.get("text") or text)
        project_id, project_block = await self._resolve_project(user_id)
        ctx, prof = await self._memory_context(user_id, text, project_id)
        from .skills import resolve_skill_block

        prof += project_block + await resolve_skill_block(user_id)
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
                    max_iters_override=max_iters_override,
                )

            await self._persist_turn(user_id, text, answer or "", resolved, iters, project_id)
            return {"text": answer or FALLBACK, "mode": resolved, "iters": iters}
        except Exception as exc:  # noqa: BLE001
            await agent_hooks.run_on_error(
                {"user_id": user_id, "text": text, "error": str(exc), "mode": resolved}
            )
            raise
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
        from . import hooks as agent_hooks

        hook_ctx = await agent_hooks.run_pre_turn(
            {"user_id": user_id, "text": text, "mode": mode or ""}
        )
        text = str(hook_ctx.get("text") or text)
        project_id, project_block = await self._resolve_project(user_id)
        ctx, prof = await self._memory_context(user_id, text, project_id)
        from .skills import resolve_skill_block

        prof += project_block + await resolve_skill_block(user_id)
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
            await self._persist_turn(user_id, text, answer or "", resolved, iters, project_id)
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
        max_iters_override: int | None = None,
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
        limit = _max_iters(computer=computer, override=max_iters_override)
        guard = _progress_guard()
        stuck_at = 0
        for i in range(1, limit + 1):
            msg = await self._llm.chat(settings.ollama_model_agent, messages, tools=tools)
            messages.append(_assistant_msg(msg))
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                calls = _parse_inline_tool_calls(content)
            if not calls:
                if content.strip():
                    yield {"delta": _ensure_tool_media(content.strip(), messages)}
                yield {"iters": i}
                return
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = coerce_args(fn.get("arguments"))
                yield {"status": _tool_status(name)}
                yield {"tool_start": {"name": name, "args": args}}
                result = await dispatch(name, args, user_id, allow_computer=allow_computer)
                from . import hooks as agent_hooks

                hook_out = await agent_hooks.run_post_tool(
                    {
                        "user_id": user_id,
                        "tool": name,
                        "args": args,
                        "result": result,
                    }
                )
                result = str(hook_out.get("result") or result)
                yield {"tool_done": {"name": name, "result": result}}
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
                if _observe_check(guard, name, result):
                    stuck_at = i
            if stuck_at:
                break

        messages.append({"role": "system", "content": _stop_note(no_progress=bool(stuck_at))})
        async for delta in self._llm.chat_stream(settings.ollama_model_agent, messages):
            yield {"delta": delta}
        yield {"iters": stuck_at or limit}

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
        max_iters_override: int | None = None,
    ) -> tuple[str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer, profile=profile)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer, allow_computer=allow_computer)
        limit = _max_iters(computer=computer, override=max_iters_override)
        guard = _progress_guard()
        stuck_at = 0
        for i in range(1, limit + 1):
            msg = await self._llm.chat(settings.ollama_model_agent, messages, tools=tools)
            messages.append(_assistant_msg(msg))
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not calls:
                # Фолбек: модель могла віддати tool call текстом (inline XML/JSON).
                calls = _parse_inline_tool_calls(content)
            if not calls:
                return _ensure_tool_media(content.strip(), messages), i
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = coerce_args(fn.get("arguments"))
                result = await dispatch(name, args, user_id, allow_computer=allow_computer)
                from . import hooks as agent_hooks

                hook_out = await agent_hooks.run_post_tool(
                    {
                        "user_id": user_id,
                        "tool": name,
                        "args": args,
                        "result": result,
                    }
                )
                result = str(hook_out.get("result") or result)
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
                if _observe_check(guard, name, result):
                    stuck_at = i
            if stuck_at:
                break

        # Стоп: no-progress (CA-3.4) або вичерпані ітерації — змусимо текстову відповідь.
        messages.append({"role": "system", "content": _stop_note(no_progress=bool(stuck_at))})
        final = await self._llm.chat(settings.ollama_model_agent, messages)
        return _ensure_tool_media((final.get("content") or "").strip(), messages), (stuck_at or limit)

    async def plan(self, user_id: int, text: str) -> dict[str, Any]:
        """Structured plan JSON → Redis (status pending) + marker для Telegram."""
        from . import plans

        prompt = (
            "Склади план виконання запиту користувача. Поверни ЛИШЕ JSON без пояснень:\n"
            '{"summary":"короткий опис","steps":[{"title":"...","detail":"..."}],'
            '"risks":["..."]}\n'
            f"Максимум {_PLAN_MAX_STEPS} кроків. Запит: {text}"
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {"role": "system", "content": "Ти планувальник задач JARVIS. Відповідай лише валідним JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        content = (msg.get("content") or "").strip()
        parsed = extract_json_object(content)
        if not parsed:
            parsed = {"summary": content[:500] or text[:200], "steps": [{"title": text[:200], "detail": text}], "risks": []}
        rec = await plans.create_plan(
            user_id,
            summary=str(parsed.get("summary") or text[:500]),
            steps=parsed.get("steps") or [],
            risks=parsed.get("risks") if isinstance(parsed.get("risks"), list) else [],
            source_text=text,
            status="pending",
        )
        rec["marker"] = PLAN_MARKER.format(id=rec["id"])
        return rec

    async def code_plan(self, user_id: int, text: str) -> dict[str, Any]:
        """Code-specific план (CA-4.1): кроки з file/action/rationale/risk → Redis (pending).

        Один апрув на весь план (CA-4.2) — наявним `approve_plan`. Виконання потім
        мапиться на `code_edit_batch` (транзакційний multi-file, CA-4.3)."""
        from . import plans

        prompt = (
            "Склади план зміни/рефактору коду. Поверни ЛИШЕ JSON без пояснень:\n"
            '{"summary":"короткий опис","steps":[{"file":"шлях до файлу",'
            '"action":"що саме зробити","rationale":"навіщо","risk":"low|medium|high"}],'
            '"risks":["загальні ризики"]}\n'
            f"Максимум {_PLAN_MAX_STEPS} кроків, КОЖЕН прив'язаний до конкретного файлу. "
            f"Запит: {text}"
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {
                    "role": "system",
                    "content": "Ти планувальник рефакторингу коду JARVIS. Відповідай лише "
                    "валідним JSON; кожен крок прив'язаний до файлу.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = (msg.get("content") or "").strip()
        parsed = extract_json_object(content) or {}
        steps = parsed.get("steps") if isinstance(parsed.get("steps"), list) else []
        if not steps:
            steps = [{"file": "", "action": text[:200], "rationale": "", "risk": "medium"}]
        rec = await plans.create_plan(
            user_id,
            summary=str(parsed.get("summary") or text[:500]),
            steps=steps,
            risks=parsed.get("risks") if isinstance(parsed.get("risks"), list) else [],
            source_text=text,
            status="pending",
            kind="code",
        )
        rec["marker"] = PLAN_MARKER.format(id=rec["id"])
        return rec

    async def _git_diff(self, path: str, ref: str = "") -> str:
        """`git -C <path> diff [ref]` через host-agent /cli (read-only)."""
        from . import computer

        args = ["-C", path, "--no-pager", "diff"]
        if ref:
            args.append(ref)
        data = await computer._request("POST", "/cli", json={"exe": "git", "args": args, "cwd": None})
        if "error" in data:
            return ""
        return str(data.get("stdout", ""))

    async def code_review(
        self, user_id: int, *, diff: str = "", path: str = "", ref: str = ""
    ) -> dict[str, Any]:
        """Self-review pass (CA-5.1): diff → структуровані зауваження + вердикт.

        diff передається напряму або тягнеться `git diff` у path (опційно vs ref).
        Повертає {verdict: clean|issues|empty, summary, findings:[{file,severity,note}]}."""
        diff_text = (diff or "").strip()
        if not diff_text and (path or "").strip():
            diff_text = (await self._git_diff(path.strip(), (ref or "").strip())).strip()
        if not diff_text:
            return {"verdict": "empty", "summary": "Немає diff для рев'ю.", "findings": []}
        diff_text = diff_text[: settings.code_review_max_chars]
        prompt = (
            "Зроби code review цього diff. Шукай: баги, регресії, витоки/секрети, "
            "пропущені краї, мертвий/дубльований код, проблеми типів. Поверни ЛИШЕ JSON:\n"
            '{"summary":"стислий вердикт","findings":[{"file":"шлях","severity":'
            '"low|medium|high","note":"проблема + як виправити"}]}\n'
            "Якщо проблем нема — порожній findings. Diff:\n" + diff_text
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {
                    "role": "system",
                    "content": "Ти прискіпливий Reviewer коду JARVIS. Відповідай лише валідним "
                    "JSON; severity тільки low/medium/high.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        parsed = extract_json_object((msg.get("content") or "").strip()) or {}
        findings = _normalize_findings(parsed.get("findings"))
        verdict = "issues" if any(f["severity"] in ("medium", "high") for f in findings) else "clean"
        return {
            "verdict": verdict,
            "summary": str(parsed.get("summary") or ("Знайдено зауваження." if findings else "Зауважень немає."))[:2000],
            "findings": findings,
        }

    async def execute_plan(self, user_id: int, plan_id: str) -> dict[str, Any]:
        """Покрокове виконання схваленого плану (sync MVP, max 8 steps)."""
        from . import plans

        rec = await plans.get_plan(plan_id)
        if rec is None or int(rec.get("user_id", 0)) != int(user_id):
            return {"error": "plan not found", "plan_id": plan_id}
        if rec.get("status") != "approved":
            return {"error": f"plan status is {rec.get('status')}, need approved", "plan": rec}
        steps = rec.get("steps") or []
        if not steps:
            await plans.finish_plan(plan_id, result="План без кроків.", status="done")
            rec = await plans.get_plan(plan_id)
            return {"plan": rec}

        await plans.set_executing(plan_id)
        outputs: list[str] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            title = str(step.get("title") or f"Крок {i + 1}")
            detail = str(step.get("detail") or title)
            step_prompt = f"Виконай крок {i + 1} з плану «{rec.get('summary', '')}»: {title}. Деталі: {detail}"
            try:
                turn = await self.run(user_id, step_prompt, mode="agent")
                answer = str(turn.get("text") or "")
                outputs.append(f"### Крок {i + 1}: {title}\n{answer}")
                await plans.advance_step(plan_id, i, status="done")
            except Exception as exc:  # noqa: BLE001
                await plans.advance_step(plan_id, i, status="failed")
                outputs.append(f"### Крок {i + 1}: {title}\nПомилка: {exc}")
                break

        result = "\n\n".join(outputs)
        await plans.finish_plan(plan_id, result=result, status="done")
        final = await plans.get_plan(plan_id)
        return {"plan": final, "result": result}
