"""Агент-луп: маршрутизація CHAT/AGENT + tool-calling на AGENT-моделі.

- AGENT_MODE=chat   → завжди легка CHAT-модель, без інструментів.
- AGENT_MODE=agent  → завжди AGENT-модель з тул-лупом.
- AGENT_MODE=hybrid → евристика: математика / URL / пошукові ключі → agent, інакше chat.
- AGENT_MODE=computer → AGENT-модель з computer-toolkit (PowerShell/CLI/FS на хості).
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from .config import settings
from .memory_client import MemoryClient
from .thread_context import build_thread_context
from .user_profile import profile_prompt_block
from jarvis_core.agent.tool_loop import ToolStepResult, run_tool_loop
from jarvis_core.agent.trace import tool_trace_entry
from jarvis_core.llm.chat import ChatBackend
from jarvis_core.llm.parsers import extract_json_object
from .toolkit import agent_tool_schemas, coerce_args, dispatch, image_gen_enabled

logger = logging.getLogger("jarvis.tools.agent")

FALLBACK = "Не зміг сформувати відповідь. Спробуй переформулювати."

PLAN_MARKER = "[[PLAN_CONFIRM:{id}]]"
_PLAN_MAX_STEPS = 8

# CA-3.2 fix-orchestration: вузький набір coding-інструментів для петлі «тест→правка→тест».
_FIX_TOOLS = frozenset(
    {
        "code_read", "repo_grep", "repo_tree", "repo_symbols", "repo_refs",
        "code_edit", "run_tests", "run_lint",
    }
)
_FIX_INNER_STEPS = 4  # модельних кроків (read/grep/edit) у межах одного раунду


def _strip_code_fences(text: str) -> str:
    """Прибирає обгортку ```lang ... ``` навколо повернутого моделлю вмісту файлу (CA-6.3)."""
    s = text.strip()
    if not s.startswith("```"):
        return text
    lines = s.split("\n")
    lines = lines[1:]  # перший рядок: ``` або ```python
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _fix_system() -> str:
    return (
        "Ти JARVIS — інженер, що лагодить падіння тестів. Працюй вузько: 1) прочитай "
        "вивід тестів і локалізуй причину (code_read/repo_grep/repo_symbols); 2) внеси "
        "мінімальну правку через code_edit (diff), не переписуй файл цілком; 3) НЕ вгадуй — "
        "спирайся на текст помилки. Після твоєї правки систему тестів буде перезапущено "
        "автоматично. Якщо причина неясна — спершу читай код, не редагуй наосліп. "
        "Відповідай українською, стисло."
    )


def _fix_user_prompt(task: str, exe: str, args: list[str], path: str, verdict: str) -> str:
    cmd = (exe + " " + " ".join(args)).strip()
    where = f" у {path}" if path else ""
    extra = f"\nКонтекст задачі: {task}" if task else ""
    return (
        f"Падають тести (команда: `{cmd}`{where}). Локалізуй і виправ диффом, "
        f"мінімально.{extra}\n\nПоточний вивід:\n{verdict}"
    )
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
# Матчимо лише ВІДКРИТТЯ об'єкта (до `{` аргументів); сам об'єкт дочитуємо
# балансувальником дужок — нежадібний `\{.*?\}` обрізав би вкладені arguments
# (mcp_call, code_edit_batch) на першій внутрішній `}` → JSONDecodeError → args={}.
_INLINE_TOOL_OPEN_RE = re.compile(
    r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*\{',
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
    "code_edit_batch": "🩹 правлю кілька файлів (diff)…",
    "repo_tree": "🌳 дерево репо…",
    "repo_grep": "🔎 шукаю в коді…",
    "code_read": "📄 читаю рядки…",
    "repo_symbols": "🧭 символи файлу…",
    "repo_refs": "🔗 шукаю посилання…",
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


def _scan_balanced_json(s: str, start: int) -> tuple[str | None, int]:
    """Від `{` у s[start] повертає (підрядок збалансованого об'єкта, індекс після нього).

    Поважає рядкові літерали та екранування, тож дужки всередині рядкових значень
    (напр. ``"a{b}c"``) не ламають баланс. Якщо об'єкт незакритий → (None, start).
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1], i + 1
    return None, start


def _parse_inline_tool_calls(content: str) -> list[dict[str, Any]]:
    """Витягує tool calls, які модель помилково віддала текстом, а не у tool_calls."""
    out: list[dict[str, Any]] = []
    text = content or ""
    pos = 0
    while True:
        m = _INLINE_TOOL_OPEN_RE.search(text, pos)
        if not m:
            break
        name = m.group(1)
        # m.start() вказує на зовнішню `{` всього об'єкта — дочитуємо його цілком.
        obj_str, end = _scan_balanced_json(text, m.start())
        if obj_str is None:
            # Незбалансовано: решта буфера — один незакритий об'єкт; жодне пізніше
            # відкриття не дасть валідного верхньорівневого виклику. Емітимо ім'я
            # (контракт фолбеку) і зупиняємось — інакше кожне наступне відкриття
            # ре-сканувало б до EOF → O(n²) на повторюваних обрізках (анти-DoS).
            out.append({"function": {"name": name, "arguments": {}}})
            break
        args: dict[str, Any] = {}
        try:
            parsed = json.loads(obj_str)
        except (json.JSONDecodeError, RecursionError):
            parsed = None  # биті дужки / надмірна вкладеність → деградуємо, не падаємо
        if isinstance(parsed, dict) and isinstance(parsed.get("arguments"), dict):
            args = parsed["arguments"]
        pos = end  # продовжуємо ПІСЛЯ цього об'єкта (не всередині нього)
        out.append({"function": {"name": name, "arguments": args}})
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


def _tool_message(name: str, result: str) -> dict[str, Any]:
    return {"role": "tool", "content": f"[{name}] {result}"}


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
        trace: list[dict[str, Any]] | None = None,
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
            model=settings.ollama_model_chat if mode == "chat" else settings.ollama_model_agent,
            trace=trace,
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
        # Споживання зібраного контексту (P9/P10, CONTEXT_MODULE §7 крок 5): паспорти
        # ambient-контексту інжектяться у промпт. За прапором — нуль latency, коли off.
        from .config import settings as _settings

        if _settings.enable_context_retrieval:
            from jarvis_core.passport import format_context_block

            passports = await self._mem.search_context(
                user_id, text, top_k=_settings.context_retrieval_top_k
            )
            block = format_context_block(passports)
            if block:
                parts.append(block)
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

        trace: list[dict[str, Any]] = []
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
                    trace=trace,
                )

            await self._persist_turn(
                user_id, text, answer or "", resolved, iters, project_id, trace=trace
            )
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
        trace: list[dict[str, Any]] = []
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
                    trace=trace,
                ):
                    if "iters" in ev:
                        iters = int(ev["iters"])
                        continue
                    if "delta" in ev:
                        parts.append(str(ev["delta"]))
                    yield ev

            answer = "".join(parts).strip()
            await self._persist_turn(
                user_id, text, answer or "", resolved, iters, project_id, trace=trace
            )
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

    def _agent_chat(
        self, tools: list[dict[str, Any]]
    ) -> "Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]":
        """Один крок AGENT-моделі з тулами — інжектується у run_tool_loop."""

        async def chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
            return await self._llm.chat(settings.ollama_model_agent, messages, tools=tools)

        return chat

    def _make_executor(
        self,
        user_id: int,
        origin_text: str,
        *,
        allow_computer: bool,
        streaming: bool,
        trace: list[dict[str, Any]] | None = None,
    ) -> "Callable[[str, Any], Awaitable[ToolStepResult]]":
        """Сервіс-специфічне виконання інструмента (dispatch + post_tool hook +
        confirm-рендеринг + лог) — інжектується у run_tool_loop. Confirm рендериться
        по-різному для sync (inline-маркер) і stream (окрема подія + людський текст).
        `trace` (AO-5.1a) — акумулятор хеш-записів кожного виклику для session-логу."""

        async def execute(name: str, args: Any) -> ToolStepResult:
            result = await dispatch(name, args, user_id, allow_computer=allow_computer)
            from . import hooks as agent_hooks

            hook_out = await agent_hooks.run_post_tool(
                {"user_id": user_id, "tool": name, "args": args, "result": result}
            )
            result = str(hook_out.get("result") or result)
            done_text = result
            if trace is not None:
                # Хешується сирий результат інструмента (до confirm-рендера з
                # випадковим кодом) — інакше хеш нестабільний між replay-ранами.
                trace.append(tool_trace_entry(name, args, result))
            event: dict[str, Any] | None = None
            confirm = _parse_confirm(result)
            if confirm:
                from .computer_confirm import save_origin

                await save_origin(user_id, origin_text)
                if streaming:
                    event = {"confirm": confirm}
                    result = (
                        f"Очікую підтвердження в Telegram (код {confirm['code']}): "
                        f"{confirm['desc']}"
                    )
                else:
                    result = (
                        f"[[COMPUTER_CONFIRM:{confirm['code']}]] "
                        f"Очікую підтвердження: {confirm['desc']}"
                    )
            logger.info("tool[%s] -> %.80s", name, result.replace("\n", " "))
            return ToolStepResult(text=result, done_text=done_text, event=event)

        return execute

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
        trace: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Тул-луп зі стрімом: статус на кожен виклик інструмента + фінальний текст.

        Тонкий споживач спільного run_tool_loop (R1). Фінальну відповідь у звичайному
        завершенні модель уже згенерувала разом із рішенням «тулів більше нема» —
        віддаємо її одним delta; лише при вичерпанні ітерацій примусова відповідь без
        тулів стрімиться токенами.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer, profile=profile)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer, allow_computer=allow_computer)
        limit = _max_iters(computer=computer, override=max_iters_override)
        async for ev in run_tool_loop(
            messages=messages,
            limit=limit,
            chat=self._agent_chat(tools),
            coerce=coerce_args,
            execute=self._make_executor(
                user_id, text, allow_computer=allow_computer, streaming=True, trace=trace
            ),
            inline_parser=_parse_inline_tool_calls,
            tool_message=_tool_message,
            emit_status=lambda name: {"status": _tool_status(name)},
        ):
            if "final" in ev:
                content = str(ev["final"])
                if content:
                    yield {"delta": _ensure_tool_media(content, messages)}
                yield {"iters": int(ev["iters"])}
                return
            if "need_final" in ev:
                messages.append(
                    {"role": "system", "content": "Дай фінальну відповідь користувачу без інструментів."}
                )
                async for delta in self._llm.chat_stream(settings.ollama_model_agent, messages):
                    yield {"delta": delta}
                yield {"iters": int(ev["iters"])}
                return
            yield ev

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
        trace: list[dict[str, Any]] | None = None,
    ) -> tuple[str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _agent_system(ctx, computer=computer, profile=profile)},
            {"role": "user", "content": text},
        ]
        tools = agent_tool_schemas(computer=computer, allow_computer=allow_computer)
        limit = _max_iters(computer=computer, override=max_iters_override)
        async for ev in run_tool_loop(
            messages=messages,
            limit=limit,
            chat=self._agent_chat(tools),
            coerce=coerce_args,
            execute=self._make_executor(
                user_id, text, allow_computer=allow_computer, streaming=False, trace=trace
            ),
            inline_parser=_parse_inline_tool_calls,
            tool_message=_tool_message,
        ):
            if "final" in ev:
                return _ensure_tool_media(str(ev["final"]), messages), int(ev["iters"])
            if "need_final" in ev:
                # Ітерації вичерпано — змусимо модель дати текстову відповідь без тулів.
                messages.append(
                    {"role": "system", "content": "Дай фінальну відповідь користувачу без інструментів."}
                )
                final = await self._llm.chat(settings.ollama_model_agent, messages)
                return _ensure_tool_media((final.get("content") or "").strip(), messages), int(ev["iters"])
        return _ensure_tool_media("", messages), limit  # недосяжно: луп завжди ʼїлдить final|need_final

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
        """Code-specific план (CA-4.1): кроки з file-targets {file, action, rationale, risk}.

        Один апрув на весь план (CA-4.2) — через звичайний approve-flow P3 (маркер).
        """
        from . import plans

        prompt = (
            "Склади план зміни коду під запит. Поверни ЛИШЕ JSON без пояснень:\n"
            '{"summary":"короткий опис","steps":[{"file":"відносний/шлях.py",'
            '"action":"що зробити у файлі","rationale":"чому","risk":"low|medium|high"}],'
            '"risks":["загальні ризики"]}\n'
            f"Максимум {_PLAN_MAX_STEPS} кроків, кожен прив'язаний до конкретного файлу. "
            f"Запит: {text}"
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {
                    "role": "system",
                    "content": (
                        "Ти планувальник змін коду JARVIS. Кожен крок прив'язаний до файлу. "
                        "Відповідай лише валідним JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = (msg.get("content") or "").strip()
        parsed = extract_json_object(content)
        if not parsed:
            parsed = {
                "summary": content[:500] or text[:200],
                "steps": [{"file": "", "action": text[:200], "rationale": text, "risk": "medium"}],
                "risks": [],
            }
        # CA-4.2: у вікні session-trust (як computer) план авто-апрувиться — без
        # ручного ✅; поза вікном — звичайний pending + confirm-маркер.
        from .computer_trust import trust_level

        auto = (await trust_level(user_id)) is not None
        rec = await plans.create_plan(
            user_id,
            summary=str(parsed.get("summary") or text[:500]),
            steps=parsed.get("steps") or [],
            risks=parsed.get("risks") if isinstance(parsed.get("risks"), list) else [],
            source_text=text,
            status="approved" if auto else "pending",
        )
        rec["marker"] = "" if auto else PLAN_MARKER.format(id=rec["id"])
        rec["kind"] = "code"
        rec["auto_approved"] = auto
        return rec

    async def code_review(
        self, user_id: int, *, diff: str = "", context: str = ""
    ) -> dict[str, Any]:
        """Self-review pass (CA-5.1): unified diff → структуровані зауваження.

        Повертає {summary, verdict: approve|changes_requested, findings:[{severity,
        file, line, comment}]}. Будівельний блок для «fix перед звітом» і P9 Reviewer.
        """
        if not (diff or "").strip():
            return {"summary": "Порожній diff — нема що рев'ювити.", "verdict": "skip", "findings": []}
        ctx = f"\nКонтекст: {context}" if context else ""
        prompt = (
            "Зроби код-рев'ю наведеного unified diff. Шукай: баги, регресії, edge-cases, "
            "відсутні перевірки, безпеку, читабельність. Поверни ЛИШЕ JSON:\n"
            '{"summary":"...","verdict":"approve|changes_requested",'
            '"findings":[{"severity":"low|medium|high","file":"шлях","line":0,"comment":"..."}]}'
            f"{ctx}\n\nDiff:\n{diff[:8000]}"
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {
                    "role": "system",
                    "content": "Ти прискіпливий код-рев'юер JARVIS. Відповідай лише валідним JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = (msg.get("content") or "").strip()
        parsed = extract_json_object(content) or {}
        raw = parsed.get("findings")
        findings: list[dict[str, Any]] = []
        for f in (raw if isinstance(raw, list) else [])[:30]:
            if not isinstance(f, dict):
                continue
            try:
                line = int(f.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
            sev = str(f.get("severity") or "medium").lower()
            findings.append(
                {
                    "severity": sev if sev in ("low", "medium", "high") else "medium",
                    "file": str(f.get("file") or "")[:200],
                    "line": line,
                    "comment": str(f.get("comment") or "")[:500],
                }
            )
        verdict = str(parsed.get("verdict") or "").lower()
        if verdict not in ("approve", "changes_requested"):
            verdict = "changes_requested" if findings else "approve"
        return {
            "summary": str(parsed.get("summary") or content[:300] or "—"),
            "verdict": verdict,
            "findings": findings,
        }

    async def code_edit_propose(
        self, user_id: int, *, path: str, instruction: str, content: str = ""
    ) -> dict[str, Any]:
        """IDE-міст (CA-6.3): запропонувати правку файлу як unified diff, БЕЗ apply.

        Редактор надсилає поточний вміст + інструкцію; модель повертає оновлений вміст,
        ми рахуємо diff локально (difflib) і віддаємо `{path, diff, proposed, changed}`.
        Inline-diff показує/застосовує сам IDE — нічого не пишемо на диск (S4, dry-run).
        """
        if not (instruction or "").strip():
            return {"path": path, "diff": "", "proposed": content, "changed": False,
                    "error": "instruction required"}
        prompt = (
            "Онови вміст файлу згідно з інструкцією. Поверни ЛИШЕ повний новий вміст файлу — "
            "без пояснень, без markdown-огорожі (```), без коментарів поза кодом.\n"
            f"Файл: {path}\nІнструкція: {instruction}\n\n--- ПОТОЧНИЙ ВМІСТ ---\n{content}"
        )
        msg = await self._llm.chat(
            settings.ollama_model_agent,
            [
                {
                    "role": "system",
                    "content": (
                        "Ти редагуєш файли коду JARVIS точковими правками. Зберігай стиль і "
                        "відступи. Виводь лише повний оновлений вміст файлу."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        proposed = _strip_code_fences((msg.get("content") or ""))
        old_lines = content.splitlines(keepends=True)
        new_lines = proposed.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}"
            )
        )
        return {
            "path": path,
            "diff": diff,
            "proposed": proposed,
            "changed": proposed != content,
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

    async def _fix_round_edit(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        user_id: int,
    ) -> None:
        """Один раунд «локалізуй+прав»: до _FIX_INNER_STEPS модельних кроків з тулами.

        Перезапуск тестів — НЕ тут (його робить fix_tests як авторитетний гейт);
        тут модель читає код і вносить правку через code_edit.
        """
        async def execute(name: str, args: Any) -> ToolStepResult:
            result = await dispatch(name, args, user_id, allow_computer=True)
            logger.info("fix.tool[%s] -> %.80s", name, result.replace("\n", " "))
            return ToolStepResult(text=result)

        async for ev in run_tool_loop(
            messages=messages,
            limit=_FIX_INNER_STEPS,
            chat=self._agent_chat(tools),
            coerce=coerce_args,
            execute=execute,
            inline_parser=_parse_inline_tool_calls,
            tool_message=_tool_message,
        ):
            # fix-раунд лише читає/править; на завершенні (final|need_final) — стоп,
            # перезапуск тестів робить fix_tests як авторитетний гейт. Tool-події ігноруємо.
            if "final" in ev or "need_final" in ev:
                return

    async def _session_diff(self, path: str) -> str:
        """Робочий git-diff робочого дерева (для post-fix self-review).

        Порожньо, якщо git/host-agent недоступні — self-review тоді тихо пропускається.
        """
        from .tools import coding_tools

        try:
            res = await coding_tools._cli("git", ["diff", "--no-color"], path or None)
        except Exception:  # noqa: BLE001
            return ""
        if not isinstance(res, dict) or res.get("error"):
            return ""
        return str(res.get("stdout") or "")[:8000]

    async def _self_review_gate(
        self,
        user_id: int,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        path: str,
        run_fn: Callable[[], Awaitable[str]],
    ) -> dict[str, Any]:
        """CA-5.1 review-перед-звітом: рев'ю робочого diff; за changes_requested із
        high/medium зауваженнями — один раунд правок «під зауваження» + re-test.

        Повертає review-дікт (+ fix_attempted/tests_after_fix), або skip, якщо diff порожній.
        """
        diff = await self._session_diff(path)
        if not diff.strip():
            return {"verdict": "skip", "summary": "Немає робочого diff для self-review.", "findings": []}
        review = await self.code_review(user_id, diff=diff, context="post-fix self-review")
        actionable = [
            f for f in review.get("findings", []) if f.get("severity") in ("high", "medium")
        ]
        if review.get("verdict") != "changes_requested" or not actionable:
            return review
        notes = "\n".join(
            f"- [{f['severity']}] {f.get('file') or '?'}:{f.get('line') or 0} {f['comment']}"
            for f in actionable
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Код-рев'ю знайшло проблеми у твоїх правках — виправ їх перед звітом, "
                    f"не ламаючи тести:\n{notes}"
                ),
            }
        )
        await self._fix_round_edit(messages, tools, user_id)
        after = await run_fn()
        review["fix_attempted"] = True
        review["tests_after_fix"] = "pass" if "✅ PASS" in after else "fail"
        return review

    async def fix_tests(
        self,
        user_id: int,
        *,
        exe: str,
        args: list[str] | None = None,
        path: str = "",
        task: str = "",
        max_rounds: int | None = None,
        review: bool = False,
    ) -> dict[str, Any]:
        """Виділена fix-orchestration (CA-3.2): тест → локалізація → code_edit → re-test.

        Стоп-умови: green / max-rounds (config `coding_fix_max_rounds`) / no-progress
        (той самий набір впалих тестів двічі поспіль). code_edit лишається за confirm/
        session-trust — петля нічого не обходить (S4).

        `review=True` (+ `CODING_REVIEW_AFTER_FIX`) → після green прогнати self-review на
        робочому diff і авто-fix зауважень перед звітом (CA-5.1). Результат у `report["review"]`.

        Повертає {status, rounds, report}: status ∈ already_green|fixed|no_progress|stuck.
        """
        from .tools import check_tools, fix_loop

        arglist = list(args or [])
        rounds = max(1, max_rounds if max_rounds is not None else settings.coding_fix_max_rounds)
        do_review = bool(review and settings.coding_review_after_fix)

        async def _run() -> str:
            return await check_tools.run_tests(exe, args=arglist, path=path, user_id=user_id)

        baseline = await _run()
        if "✅ PASS" in baseline:
            return {"status": "already_green", "rounds": 0, "report": baseline}

        tools = [
            s
            for s in agent_tool_schemas(computer=True, allow_computer=True)
            if s.get("function", {}).get("name") in _FIX_TOOLS
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _fix_system()},
            {"role": "user", "content": _fix_user_prompt(task, exe, arglist, path, baseline)},
        ]

        prev_sig = fix_loop.summary_signature(baseline)
        verdict = baseline
        for rnd in range(1, rounds + 1):
            await self._fix_round_edit(messages, tools, user_id)
            verdict = await _run()
            if "✅ PASS" in verdict:
                out: dict[str, Any] = {"status": "fixed", "rounds": rnd, "report": verdict}
                if do_review:
                    out["review"] = await self._self_review_gate(
                        user_id, messages, tools, path, _run
                    )
                return out
            sig = fix_loop.summary_signature(verdict)
            if sig == prev_sig:
                return {"status": "no_progress", "rounds": rnd, "report": verdict}
            prev_sig = sig
            messages.append(
                {
                    "role": "user",
                    "content": f"Тести все ще падають — спробуй інший підхід:\n{verdict}",
                }
            )
        return {"status": "stuck", "rounds": rounds, "report": verdict}
