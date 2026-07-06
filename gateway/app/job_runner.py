"""Scheduled remote jobs poller — виконує macro o due time."""
from __future__ import annotations

import asyncio
import logging

from .telegram import TelegramClient
from .tools_client import ToolsClient

logger = logging.getLogger("jarvis.gateway.job_runner")


async def _run_due_jobs(tools: ToolsClient, tg: TelegramClient) -> int:
    try:
        jobs = await tools.due_jobs()
    except Exception as exc:  # noqa: BLE001
        logger.warning("due jobs fetch failed: %s", exc)
        return 0
    sent = 0
    for job in jobs:
        uid = int(job.get("user_id", 0))
        macro = str(job.get("macro", ""))
        if not uid or not macro:
            continue
        try:
            result = await tools.run_macro(uid, macro)
            await tg.send_message(uid, f"⏰ Job `{macro}`:\n{result[:3500]}")
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("job %s failed: %s", macro, exc)
    return sent


async def job_runner_loop(
    tools: ToolsClient,
    tg: TelegramClient,
    interval: float = 30.0,
) -> None:
    logger.info("Job runner started (interval=%ss)", interval)
    while True:
        try:
            await _run_due_jobs(tools, tg)
        except asyncio.CancelledError:
            logger.info("Job runner stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("job runner tick failed: %s", exc)
        await asyncio.sleep(interval)
