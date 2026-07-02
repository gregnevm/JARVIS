"""Авто-запис діалогів у JSONL для Twin / training (Фаза 3 A.2)."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from jarvis_core.agent.trace import short_hash
from jarvis_core.llm.jsonl_log import JsonlLog

from .config import settings

logger = logging.getLogger("jarvis.tools.session_ingest")


def _log_path(user_id: int) -> Path:
    base = Path(settings.data_dir) / "logs" / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"user_{int(user_id)}.jsonl"


def append_turn(
    user_id: int,
    *,
    user_text: str,
    assistant_text: str,
    mode: str,
    iters: int = 0,
    model: str = "",
    trace: list[dict[str, Any]] | None = None,
) -> None:
    if int(user_id) <= 0:
        return
    # AO-5.1a: input_hash — по повному тексту (не по обрізаному [:4000] "user"),
    # бо replay порівнює те, що реально пішло в модель. model/trace — опційні,
    # щоб не роздувати записи режиму chat (там тулів нема).
    record: dict[str, Any] = {
        "ts": int(time.time()),
        "user_id": int(user_id),
        "mode": mode,
        "iters": int(iters),
        "user": (user_text or "")[:4000],
        "assistant": (assistant_text or "")[:8000],
        "input_hash": short_hash(user_text or ""),
    }
    if model:
        record["model"] = model
    if trace:
        record["trace"] = trace
    try:
        JsonlLog(_log_path(user_id)).append(record)
    except OSError as exc:
        logger.warning("session log append failed: %s", exc)
        return
    try:
        asyncio.get_running_loop().create_task(_push_twin(user_id, record))
    except RuntimeError:
        pass


async def _push_twin(user_id: int, record: dict[str, Any]) -> None:
    twin = (settings.twin_url or "").strip()
    if not twin:
        return
    edge_id = f"hq-{int(user_id)}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as cli:
            await cli.post(
                f"{twin.rstrip('/')}/ingest/logs",
                json={"edge_id": edge_id, "delta_start_idx": 0, "logs": [record]},
            )
    except httpx.HTTPError as exc:
        logger.debug("twin ingest skip: %s", exc)
