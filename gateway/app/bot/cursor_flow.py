"""Telegram → Cursor IDE: черга задач і режим «надішли наступне повідомлення»."""
from __future__ import annotations

import logging
import re
from typing import Any

import redis.asyncio as aioredis

from ..auth import is_admin
from ..services import ServicesClient
from ..telegram import TelegramClient
from ..tools_client import ToolsClient
from .dashboard import esc

logger = logging.getLogger("jarvis.gateway.bot.cursor")

_AWAIT = "jarvis:cursor:await:{user_id}"
_AWAIT_TTL = 600

_CURSOR_PREFIX_RE = re.compile(
    r"^(?:cursor|курсор)\s*(?:задач\w*)?\s*(?:[:\-]\s*|\s+)(.+)",
    re.IGNORECASE | re.DOTALL,
)


def can_use_cursor(user_id: int | None) -> bool:
    return is_admin(user_id)


def try_extract_cursor_task(text: str, *, computer_mode: bool = False) -> str | None:
    """Витягує задачу з «cursor: …» / «cursor …». У computer mode — також «cursor задача …»."""
    raw = (text or "").strip()
    if not raw:
        return None
    m = _CURSOR_PREFIX_RE.match(raw)
    if m:
        return m.group(1).strip()
    if computer_mode and re.search(r"\b(?:cursor|курсор)\b", raw, re.IGNORECASE):
        cleaned = re.sub(
            r"^(?:.*?\b(?:cursor|курсор)\b\s*(?:задач\w*)?\s*[:\-]?\s*)",
            "",
            raw,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()
        return cleaned or raw
    return None


async def set_await(redis: aioredis.Redis, user_id: int) -> None:
    await redis.set(_AWAIT.format(user_id=user_id), "1", ex=_AWAIT_TTL)


async def clear_await(redis: aioredis.Redis, user_id: int) -> None:
    await redis.delete(_AWAIT.format(user_id=user_id))


async def is_awaiting(redis: aioredis.Redis, user_id: int) -> bool:
    return bool(await redis.get(_AWAIT.format(user_id=user_id)))


async def submit_task(
    chat_id: int,
    user_id: int,
    task: str,
    tg: TelegramClient,
    tools: ToolsClient,
    *,
    redis: aioredis.Redis | None = None,
) -> bool:
    task = (task or "").strip()
    if not task:
        await tg.send_message(chat_id, "Порожня задача.")
        return False
    if not can_use_cursor(user_id):
        await tg.send_message(chat_id, "⛔ Cursor — лише для адмінів.")
        return False
    job = await tools.create_cursor_job(user_id, task)
    if job.get("error"):
        await tg.send_message(chat_id, f"🔴 {esc(str(job['error']))}", parse_mode="HTML")
        return False
    if redis is not None:
        await clear_await(redis, user_id)
    jid = esc(str(job.get("id") or "?"))
    await tg.send_message(
        chat_id,
        f"🧠 Cursor <code>{jid}</code> в черзі.\n{esc(task[:800])}\n\n"
        "Результат прийде сюди. Статус: <code>/cursor status</code>",
        parse_mode="HTML",
    )
    return True


async def format_status(tools: ToolsClient, user_id: int) -> str:
    jobs = await tools.list_bg_jobs(user_id, limit=15)
    cursor_jobs = [j for j in jobs if str(j.get("type") or "") == "cursor_task"]
    if not cursor_jobs:
        return "🧠 Cursor: немає задач у черзі/історії."
    lines = ["🧠 <b>Cursor задачі</b>"]
    for j in cursor_jobs[:8]:
        st = esc(str(j.get("status") or "?"))
        jid = esc(str(j.get("id") or "?"))
        raw_payload = j.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        task = esc(str(payload.get("task") or "")[:80])
        lines.append(f"• <code>{jid}</code> {st} — {task}")
    lines.append("\nСкасувати: <code>/cursor cancel &lt;id&gt;</code>")
    return "\n".join(lines)


async def handle_cursor_command(
    raw: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    redis: aioredis.Redis | None,
) -> bool:
    if not can_use_cursor(user_id):
        await tg.send_message(chat_id, "⛔ /cursor — лише для адмінів (ADMIN_USER_IDS).")
        return True
    parts = raw.split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "status":
        await tg.send_message(chat_id, await format_status(tools, user_id), parse_mode="HTML")
        return True

    if sub == "cancel" and len(parts) > 2:
        job_id = parts[2].strip()
        ok = await tools.cancel_bg_job(job_id, user_id)
        await tg.send_message(
            chat_id,
            f"{'✅ скасовано' if ok else '🔴 не знайдено'} <code>{esc(job_id)}</code>",
            parse_mode="HTML",
        )
        return True

    if sub in ("ask", "wait", "new"):
        if redis is None:
            await tg.send_message(chat_id, "Redis недоступний.")
            return True
        await set_await(redis, user_id)
        await tg.send_message(
            chat_id,
            "🧠 <b>Cursor mode</b>\nНадішли одним повідомленням задачу для Cursor IDE "
            "(код, рефакторинг, тести…).\nСкасувати: <code>/cursor off</code>",
            parse_mode="HTML",
        )
        return True

    if sub in ("off", "stop", "exit"):
        if redis is not None:
            await clear_await(redis, user_id)
        await tg.send_message(chat_id, "Cursor mode вимкнено.")
        return True

    task = raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) > 1 else ""
    if not task:
        await tg.send_message(
            chat_id,
            "🧠 <b>Керування Cursor з Telegram</b>\n\n"
            "<code>/cursor &lt;задача&gt;</code> — поставити в чергу\n"
            "<code>/cursor ask</code> — наступне повідомлення = задача\n"
            "<code>/cursor status</code> — статус задач\n"
            "<code>/cursor cancel &lt;id&gt;</code> — скасувати\n\n"
            "<b>Computer mode:</b> <code>/mode computer</code> → "
            "<code>cursor: &lt;задача&gt;</code>\n\n"
            "Приклад:\n<code>/cursor додай тести для cursor_tasks.py</code>",
            parse_mode="HTML",
        )
        return True

    await submit_task(chat_id, user_id, task, tg, tools, redis=redis)
    return True


async def try_computer_cursor_message(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    svc: ServicesClient,
    *,
    redis: aioredis.Redis | None = None,
) -> bool:
    """Computer Use: «cursor: задача» → одразу в чергу Cursor (без LLM tool-loop)."""
    if not can_use_cursor(user_id):
        return False
    dash = await svc.dashboard()
    mode = str(dash.get("agent_mode") or "").lower()
    computer_mode = mode == "computer"
    task = try_extract_cursor_task(text, computer_mode=computer_mode)
    if not task:
        return False
    await submit_task(chat_id, user_id, task, tg, tools, redis=redis)
    return True


async def try_awaiting_message(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    redis: aioredis.Redis,
) -> bool:
    if not await is_awaiting(redis, user_id):
        return False
    if text.strip().startswith("/"):
        return False
    await submit_task(chat_id, user_id, text, tg, tools, redis=redis)
    return True
