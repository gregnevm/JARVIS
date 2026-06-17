"""Background agent job worker — dequeue з tools і notify у Telegram."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis_core.bg_jobs import JOB_TYPES

from .telegram import TelegramClient
from .tools_client import ToolsClient

logger = logging.getLogger("jarvis.gateway.bg_job_runner")

JobHandler = Callable[[ToolsClient, TelegramClient, str, int, dict[str, Any]], Awaitable[None]]


async def _handle_deep_research(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    query = str(payload.get("query") or "")
    max_hops = int(payload.get("max_hops") or 3)
    if not uid or not query:
        await tools.finish_bg_job(job_id, error="invalid research payload", status="failed")
        return
    try:
        result = await tools.run_research(job_id, uid, query, max_hops)
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Research {job_id}: {result['error']}")
        else:
            report = str(result.get("report") or "")[:3500]
            await tg.send_message(
                uid,
                f"✅ Research <code>{job_id}</code> готово:\n{report}",
                parse_mode="HTML",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg research job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")
        try:
            await tg.send_message(uid, f"❌ Research {job_id} помилка: {exc}")
        except Exception:  # noqa: BLE001
            pass


async def _handle_subagent(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    task = str(payload.get("task") or "")
    budget = int(payload.get("budget_iters") or 3)
    run_id = str(payload.get("run_id") or "")
    mode = str(payload.get("mode") or "agent")
    if not uid or not task:
        await tools.finish_bg_job(job_id, error="invalid subagent payload", status="failed")
        return
    try:
        result = await tools.run_subagent(job_id, uid, run_id, task, budget, mode)
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Subagent {run_id}: {result['error']}")
        else:
            preview = str(result.get("result") or "")[:3500]
            await tg.send_message(
                uid,
                f"✅ Subagent <code>{run_id}</code>:\n{preview}",
                parse_mode="HTML",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg subagent job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


async def _handle_agent_team(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    task = str(payload.get("task") or "")
    team_id = str(payload.get("team_id") or "")
    if not uid or not task or not team_id:
        await tools.finish_bg_job(job_id, error="invalid team payload", status="failed")
        return
    try:
        result = await tools.run_team(job_id, uid, team_id)
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Team {team_id}: {result['error']}")
        else:
            preview = str(result.get("result") or "")[:3500]
            await tg.send_message(
                uid,
                f"✅ Team <code>{team_id}</code>:\n{preview}",
                parse_mode="HTML",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg team job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


async def _handle_orchestrator(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    task = str(payload.get("task") or "")
    run_id = str(payload.get("run_id") or "")
    if not uid or not task or not run_id:
        await tools.finish_bg_job(job_id, error="invalid orchestrator payload", status="failed")
        return
    try:
        result = await tools.run_orchestrator(job_id, uid, run_id)
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Orchestrator {run_id}: {result['error']}")
        else:
            preview = str(result.get("result") or "")[:3500]
            approved = "✅" if result.get("approved") else "⚠️"
            await tg.send_message(
                uid,
                f"{approved} Orchestrator <code>{run_id}</code>:\n{preview}",
                parse_mode="HTML",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg orchestrator job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


async def _handle_cursor_task(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    task = str(payload.get("task") or "")
    if not uid or not task:
        await tools.finish_bg_job(job_id, error="invalid cursor payload", status="failed")
        return
    try:
        result = await tools.run_cursor_task(task, uid)
        preview = str(result.get("text") or "")[:3500]
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Cursor {job_id}:\n{preview}", parse_mode="HTML")
        else:
            await tools.finish_bg_job(job_id, result=preview, status="done")
            await tg.send_message(uid, f"🧠 Cursor <code>{job_id}</code>:\n{preview}", parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg cursor job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


async def _handle_coding_task(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    """CA-5.3: довга coding-задача → `/agent/code/fix` (fix_tests) як headless-прогін."""
    exe = str(payload.get("exe") or "").strip()
    if not uid or not exe:
        await tools.finish_bg_job(job_id, error="invalid coding payload", status="failed")
        return
    raw_args = payload.get("args")
    args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
    path = str(payload.get("path") or "")
    task = str(payload.get("task") or "")
    max_rounds = int(payload.get("max_rounds") or 0)
    try:
        result = await tools.run_coding_task(
            job_id, uid, exe=exe, args=args, path=path, task=task, max_rounds=max_rounds
        )
        if result.get("error"):
            await tools.finish_bg_job(job_id, error=str(result["error"])[:500], status="failed")
            await tg.send_message(uid, f"❌ Coding {job_id}: {result['error']}")
            return
        status = str(result.get("status") or "?")
        report = str(result.get("report") or "")[:3200]
        summary = f"status={status} rounds={result.get('rounds', 0)}\n{report}"
        # policy_denied/stuck/no_progress — не помилка інфраструктури, лишаємо job done зі звітом.
        await tools.finish_bg_job(job_id, result=summary[:3500], status="done")
        icon = "✅" if status in ("fixed", "already_green") else "⚠️"
        await tg.send_message(
            uid,
            f"{icon} Coding <code>{job_id}</code>:\n{summary}",
            parse_mode="HTML",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg coding job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


async def _handle_agent_turn(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    text = str(payload.get("text") or "")
    mode = str(payload.get("mode") or "auto")
    if not uid or not text:
        await tools.finish_bg_job(job_id, error="invalid job payload", status="failed")
        return
    try:
        result = await tools.process({"user_id": uid, "text": text, "mode": mode})
        await tools.finish_bg_job(job_id, result=result, status="done")
        preview = (result or "")[:3500]
        await tg.send_message(uid, f"✅ Job <code>{job_id}</code> завершено:\n{preview}", parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg job %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")
        try:
            await tg.send_message(uid, f"❌ Job {job_id} помилка: {exc}")
        except Exception:  # noqa: BLE001
            pass


async def _handle_delegate_tick(
    tools: ToolsClient, tg: TelegramClient, job_id: str, uid: int, payload: dict[str, Any]
) -> None:
    """Проактивний тік делегата (Стовп D TC-5): daily-brief / watcher.

    S4-безпечно: лише READ-ONLY рушій — делегат міркує над контекстом principal і
    НОТИФІКУЄ (нічого не виконує без ✅). Мутуючі/зовнішні пропозиції підтверджує
    principal окремо (proactive.gate на боці агента).
    """
    principal = str(payload.get("principal_id") or uid or "")
    if not principal:
        await tools.finish_bg_job(job_id, error="invalid delegate payload", status="failed")
        return
    prompt = (
        "Ти проактивний делегат. Переглянь свіжий контекст і команду principal та дай "
        "стислий daily-brief: що потребує уваги, хто чекає відповіді, які кроки "
        "забуксували. Лише підсумок і пропозиції — нічого не виконуй."
    )
    try:
        brief = await tools.process({"user_id": int(uid or 0), "text": prompt, "mode": "agent"})
        await tools.finish_bg_job(job_id, result=(brief or "")[:3500], status="done")
        if brief:
            await tg.send_message(uid, f"🔔 Делегат — daily brief:\n{brief[:3500]}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg delegate tick %s failed: %s", job_id, exc)
        await tools.finish_bg_job(job_id, error=str(exc)[:500], status="failed")


_JOB_HANDLERS: dict[str, JobHandler] = {
    "deep_research": _handle_deep_research,
    "subagent": _handle_subagent,
    "agent_team": _handle_agent_team,
    "orchestrator": _handle_orchestrator,
    "cursor_task": _handle_cursor_task,
    "coding_task": _handle_coding_task,
    "delegate_tick": _handle_delegate_tick,
    "agent_turn": _handle_agent_turn,
}


async def _run_one_bg_job(tools: ToolsClient, tg: TelegramClient) -> bool:
    try:
        job = await tools.dequeue_bg_job()
    except Exception as exc:  # noqa: BLE001
        logger.warning("bg job dequeue failed: %s", exc)
        return False
    if not job:
        return False
    job_id = str(job.get("id") or "")
    uid = int(job.get("user_id") or 0)
    job_type = str(job.get("type") or "agent_turn")
    raw_payload = job.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

    handler = _JOB_HANDLERS.get(job_type, _handle_agent_turn)
    if job_type not in JOB_TYPES:
        logger.warning("unknown bg job type %s, using agent_turn handler", job_type)
    await handler(tools, tg, job_id, uid, payload)
    return True


async def bg_job_runner_loop(
    tools: ToolsClient,
    tg: TelegramClient,
    interval: float = 3.0,
) -> None:
    logger.info("Background job runner started (interval=%ss)", interval)
    while True:
        try:
            ran = await _run_one_bg_job(tools, tg)
            if not ran:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Background job runner stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("bg job runner tick failed: %s", exc)
            await asyncio.sleep(interval)


async def run_bg_job_once(tools: ToolsClient, tg: TelegramClient) -> bool:
    """Для тестів — один dequeue/run цикл."""
    return await _run_one_bg_job(tools, tg)
