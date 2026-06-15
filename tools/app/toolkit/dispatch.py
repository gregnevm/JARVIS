"""Table-driven tool dispatch for the agent loop."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import settings
from .image import describe_image, generate_image, ocr_image
from .notes import recall_notes, take_note
from .schemas import COMPUTER_TOOL_NAMES
from .web import calc, code_exec, parse_file, web_fetch, web_search

logger = logging.getLogger("jarvis.tools")

Handler = Callable[[dict[str, Any], int], Awaitable[str]]


async def _h_calc(args: dict[str, Any], _uid: int) -> str:
    return calc(str(args.get("expression", "")))


async def _h_web_search(args: dict[str, Any], _uid: int) -> str:
    return await web_search(str(args.get("query", "")))


async def _h_web_fetch(args: dict[str, Any], _uid: int) -> str:
    return await web_fetch(str(args.get("url", "")))


async def _h_parse_file(args: dict[str, Any], _uid: int) -> str:
    return parse_file(str(args.get("path", "")))


async def _h_ocr_image(args: dict[str, Any], _uid: int) -> str:
    return await asyncio.to_thread(ocr_image, str(args.get("path", "")))


async def _h_describe_image(args: dict[str, Any], _uid: int) -> str:
    return await describe_image(str(args.get("path", "")), str(args.get("question", "")))


async def _h_generate_image(args: dict[str, Any], _uid: int) -> str:
    return await generate_image(str(args.get("prompt", "")))


async def _h_code_exec(args: dict[str, Any], _uid: int) -> str:
    return await asyncio.to_thread(code_exec, str(args.get("code", "")))


async def _h_take_note(args: dict[str, Any], uid: int) -> str:
    return take_note(str(args.get("text", "")), uid)


async def _h_recall_notes(args: dict[str, Any], uid: int) -> str:
    raw_limit = args.get("limit", 10)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 10
    return recall_notes(uid, limit)


async def _h_set_reminder(args: dict[str, Any], uid: int) -> str:
    from ..reminders import add_reminder

    try:
        delay = int(args.get("delay_minutes", 0))
    except (TypeError, ValueError):
        delay = 0
    return await add_reminder(uid, delay, str(args.get("text", "")))


async def _h_list_reminders(_args: dict[str, Any], uid: int) -> str:
    from ..reminders import list_reminders

    return await list_reminders(uid)


async def _h_cancel_reminder(args: dict[str, Any], uid: int) -> str:
    from ..reminders import cancel_all_reminders, cancel_reminder

    rid = str(args.get("reminder_id", "")).strip()
    if rid.lower() in ("all", "*"):
        return await cancel_all_reminders(uid)
    return await cancel_reminder(uid, rid)


async def _h_show_in_app(args: dict[str, Any], uid: int) -> str:
    from ..artifacts import show_in_app

    return await show_in_app(
        uid,
        str(args.get("kind", "")),
        str(args.get("content", "")),
        str(args.get("title", "")),
    )


async def _h_run_powershell(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.run_powershell(
        str(args.get("script", "")), bool(args.get("as_admin", False)), user_id=uid
    )


async def _h_run_cli(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    raw_args = args.get("args", [])
    cli_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
    cwd = str(args.get("cwd", "")) or None
    return await computer.run_cli(str(args.get("exe", "")), cli_args, cwd, user_id=uid)


async def _h_fs_list(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.fs_list(str(args.get("path", "")), user_id=uid)


async def _h_fs_read(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.fs_read(str(args.get("path", "")), user_id=uid)


async def _h_fs_write(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.fs_write(
        str(args.get("path", "")), str(args.get("content", "")), user_id=uid
    )


async def _h_code_edit(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.code_edit(
        str(args.get("path", "")),
        mode=str(args.get("mode", "search_replace")),
        old_string=str(args.get("old_string", "")),
        new_string=str(args.get("new_string", "")),
        diff=str(args.get("diff", "")),
        replace_all=bool(args.get("replace_all", False)),
        user_id=uid,
    )


async def _h_capture_screenshot(_args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.capture_screenshot(user_id=uid)


async def _h_see_screen(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.see_screen(str(args.get("question", "")), user_id=uid)


async def _h_clipboard_read(_args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.clipboard_read(user_id=uid)


async def _h_clipboard_write(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.clipboard_write(str(args.get("text", "")), user_id=uid)


async def _h_browser_open(args: dict[str, Any], _uid: int) -> str:
    from .. import browser

    return await browser.browser_open(str(args.get("url", "")))


async def _h_browser_read(_args: dict[str, Any], _uid: int) -> str:
    from .. import browser

    return await browser.browser_read()


async def _h_browser_click(args: dict[str, Any], uid: int) -> str:
    from .. import browser
    from ..computer_confirm import wrap_execute

    sel = str(args.get("selector", ""))
    return await wrap_execute(uid, "browser_click", {"selector": sel}, lambda: browser.browser_click(sel))


async def _h_browser_fill(args: dict[str, Any], uid: int) -> str:
    from .. import browser
    from ..computer_confirm import wrap_execute

    sel = str(args.get("selector", ""))
    val = str(args.get("value", ""))
    return await wrap_execute(
        uid, "browser_fill", {"selector": sel, "value": val}, lambda: browser.browser_fill(sel, val)
    )


async def _h_browser_eval(args: dict[str, Any], _uid: int) -> str:
    from .. import browser

    return await browser.browser_eval(str(args.get("js", "")))


async def _h_window_list(_args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.window_list(user_id=uid)


async def _h_window_focus(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.window_focus(str(args.get("title", "")), user_id=uid)


async def _h_uia_invoke(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    return await computer.uia_invoke(
        str(args.get("window", "")),
        str(args.get("control_name", "")),
        str(args.get("action", "click")),
        user_id=uid,
    )


async def _h_screen_click(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    try:
        x = int(args.get("x", 0))
        y = int(args.get("y", 0))
    except (TypeError, ValueError):
        return "invalid coordinates"
    return await computer.screen_click(x, y, user_id=uid)


async def _h_screen_type(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    try:
        interval = int(args.get("interval_ms", 0) or 0)
    except (TypeError, ValueError):
        interval = 0
    return await computer.screen_type(str(args.get("text", "")), interval, user_id=uid)


async def _h_screen_hotkey(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    raw = args.get("keys", [])
    keys = [str(k) for k in raw] if isinstance(raw, list) else []
    return await computer.screen_hotkey(keys, user_id=uid)


async def _h_screen_scroll(args: dict[str, Any], uid: int) -> str:
    from .. import computer

    try:
        clicks = int(args.get("clicks", 0))
    except (TypeError, ValueError):
        return "invalid clicks"
    x = args.get("x")
    y = args.get("y")
    try:
        xi = int(x) if x is not None else None
        yi = int(y) if y is not None else None
    except (TypeError, ValueError):
        xi, yi = None, None
    return await computer.screen_scroll(clicks, xi, yi, user_id=uid)


async def _h_schedule_job(args: dict[str, Any], uid: int) -> str:
    from ..jobs import schedule_job

    try:
        delay = int(args.get("delay_minutes", 0))
    except (TypeError, ValueError):
        delay = 0
    run_at = int(time.time()) + delay * 60
    jid = await schedule_job(uid, run_at, str(args.get("macro", "")), str(args.get("note", "")))
    return f"Job заплановано ({jid}) через {delay} хв."


async def _h_mcp_call(args: dict[str, Any], _uid: int) -> str:
    from .. import mcp_gateway

    raw_arguments = args.get("arguments")
    arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
    return await mcp_gateway.call_tool(
        str(args.get("server", "")),
        str(args.get("tool", "")),
        arguments,
    )


async def _h_notion_search(args: dict[str, Any], _uid: int) -> str:
    from ..connectors import notion

    return await notion.search(str(args.get("query", "")))


async def _h_notion_read_page(args: dict[str, Any], _uid: int) -> str:
    from ..connectors import notion

    return await notion.read_page(str(args.get("page_id", "")))


async def _h_slack_post_message(args: dict[str, Any], _uid: int) -> str:
    from ..connectors import slack

    return await slack.post_message(str(args.get("text", "")), str(args.get("channel", "")))


async def _h_slack_list_channels(_args: dict[str, Any], _uid: int) -> str:
    from ..connectors import slack

    return await slack.list_channels()


async def _h_calendar_upcoming(args: dict[str, Any], uid: int) -> str:
    from ..connectors import calendar

    try:
        days = int(args.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    return await calendar.upcoming(days, user_id=uid)


async def _h_spawn_subagent(args: dict[str, Any], uid: int) -> str:
    from .. import bg_jobs, subagents

    task = str(args.get("task") or "")
    try:
        budget = int(args.get("budget_iters", settings.subagent_default_budget))
    except (TypeError, ValueError):
        budget = settings.subagent_default_budget
    budget = max(1, min(budget, settings.subagent_max_budget))
    rec = await subagents.create_spawn(uid, task, budget_iters=budget)
    job = await bg_jobs.create_subagent_job(uid, task, budget_iters=budget, run_id=rec["id"])
    return f"Subagent {rec['id']} queued (job {job.get('id')}). Budget={budget} iters."


async def _h_cursor_task(args: dict[str, Any], uid: int) -> str:
    from .. import cursor_tasks

    task = str(args.get("task") or "")
    async_mode = bool(args.get("async_mode", True))
    result = await cursor_tasks.submit(uid, task, async_mode=async_mode)
    return cursor_tasks.format_result(result)


async def _h_continue_dev(args: dict[str, Any], uid: int) -> str:
    from ..tools.continue_tool import run

    return await run(
        str(args.get("action") or ""),
        path=str(args.get("path") or ""),
        prompt=str(args.get("prompt") or ""),
        user_id=uid,
    )


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def _h_repo_tree(args: dict[str, Any], uid: int) -> str:
    from ..tools.coding_tools import repo_tree

    return await repo_tree(
        str(args.get("path") or ""),
        max_depth=_as_int(args.get("max_depth")) or 3,
        user_id=uid,
    )


async def _h_repo_grep(args: dict[str, Any], uid: int) -> str:
    from ..tools.coding_tools import repo_grep

    return await repo_grep(
        str(args.get("pattern") or ""),
        path=str(args.get("path") or ""),
        glob=str(args.get("glob") or ""),
        max_results=_as_int(args.get("max_results")),
        user_id=uid,
    )


async def _h_code_read(args: dict[str, Any], uid: int) -> str:
    from ..tools.coding_tools import code_read

    return await code_read(
        str(args.get("path") or ""),
        start_line=_as_int(args.get("start_line")),
        end_line=_as_int(args.get("end_line")),
        user_id=uid,
    )


async def _h_repo_symbols(args: dict[str, Any], uid: int) -> str:
    from ..tools.coding_tools import repo_symbols

    return await repo_symbols(
        str(args.get("path") or ""),
        pattern=str(args.get("pattern") or ""),
        user_id=uid,
    )


async def _h_run_tests(args: dict[str, Any], uid: int) -> str:
    from ..tools.check_tools import run_tests

    return await run_tests(
        str(args.get("exe") or ""),
        args=args.get("args"),
        path=str(args.get("path") or ""),
        framework=str(args.get("framework") or "auto"),
        user_id=uid,
    )


async def _h_run_lint(args: dict[str, Any], uid: int) -> str:
    from ..tools.check_tools import run_lint

    return await run_lint(
        str(args.get("exe") or ""),
        args=args.get("args"),
        path=str(args.get("path") or ""),
        tool=str(args.get("tool") or "auto"),
        user_id=uid,
    )


_HANDLERS: dict[str, Handler] = {
    "calc": _h_calc,
    "web_search": _h_web_search,
    "web_fetch": _h_web_fetch,
    "parse_file": _h_parse_file,
    "ocr_image": _h_ocr_image,
    "describe_image": _h_describe_image,
    "generate_image": _h_generate_image,
    "code_exec": _h_code_exec,
    "take_note": _h_take_note,
    "recall_notes": _h_recall_notes,
    "set_reminder": _h_set_reminder,
    "list_reminders": _h_list_reminders,
    "cancel_reminder": _h_cancel_reminder,
    "show_in_app": _h_show_in_app,
    "run_powershell": _h_run_powershell,
    "run_cli": _h_run_cli,
    "fs_list": _h_fs_list,
    "fs_read": _h_fs_read,
    "fs_write": _h_fs_write,
    "code_edit": _h_code_edit,
    "capture_screenshot": _h_capture_screenshot,
    "see_screen": _h_see_screen,
    "clipboard_read": _h_clipboard_read,
    "clipboard_write": _h_clipboard_write,
    "browser_open": _h_browser_open,
    "browser_read": _h_browser_read,
    "browser_click": _h_browser_click,
    "browser_fill": _h_browser_fill,
    "browser_eval": _h_browser_eval,
    "window_list": _h_window_list,
    "window_focus": _h_window_focus,
    "uia_invoke": _h_uia_invoke,
    "screen_click": _h_screen_click,
    "screen_type": _h_screen_type,
    "screen_hotkey": _h_screen_hotkey,
    "screen_scroll": _h_screen_scroll,
    "schedule_job": _h_schedule_job,
    "mcp_call": _h_mcp_call,
    "notion_search": _h_notion_search,
    "notion_read_page": _h_notion_read_page,
    "slack_post_message": _h_slack_post_message,
    "slack_list_channels": _h_slack_list_channels,
    "calendar_upcoming": _h_calendar_upcoming,
    "spawn_subagent": _h_spawn_subagent,
    "cursor_task": _h_cursor_task,
    "continue_dev": _h_continue_dev,
    "repo_tree": _h_repo_tree,
    "repo_grep": _h_repo_grep,
    "code_read": _h_code_read,
    "repo_symbols": _h_repo_symbols,
    "run_tests": _h_run_tests,
    "run_lint": _h_run_lint,
}

_CONTINUE_DEV_TOOLS = frozenset({"continue_dev"})
# Owner-gated як continue_dev: ходять через host-agent FS/CLI (той самий computer-кордон).
_CODING_TOOLS = frozenset(
    {"repo_tree", "repo_grep", "code_read", "repo_symbols", "run_tests", "run_lint"}
)


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    user_id: int = 0,
    *,
    allow_computer: bool = True,
) -> str:
    """Викликає інструмент за іменем. Помилки повертаються текстом (модель їх читає)."""
    if name in COMPUTER_TOOL_NAMES or name in _CONTINUE_DEV_TOOLS or name in _CODING_TOOLS:
        from ..computer_access import computer_denied_message
        from ..computer_profile import computer_tool_names

        denied = computer_denied_message(user_id)
        if denied or not allow_computer:
            return denied or (
                "Керування цим комп'ютером доступне лише власнику "
                "(COMPUTER_OWNER_USER_IDS у .env)."
            )
        allowed = computer_tool_names(computer=True) | {"capture_screenshot"}
        if name in COMPUTER_TOOL_NAMES and name not in allowed:
            from ..config import settings

            return (
                f"Інструмент {name} недоступний у COMPUTER_PROFILE="
                f"{settings.computer_profile!r}. Див. docs/AGENT_MODE_ROADMAP.md."
            )
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Невідомий інструмент: {name}"
    t0 = time.perf_counter()
    try:
        return await handler(arguments, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s failed", name)
        return f"Інструмент {name} впав: {exc}"
    finally:
        from ..metrics import record_tool

        await record_tool(name, (time.perf_counter() - t0) * 1000)


def coerce_args(raw: Any) -> dict[str, Any]:
    """Аргументи від Ollama бувають dict або JSON-рядком — нормалізуємо в dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
