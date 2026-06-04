"""Аудит Computer Use → data/logs/computer.jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from jarvis_core.llm.jsonl_log import JsonlLog

from .config import settings


def _log_path() -> Path:
    return Path(settings.data_dir) / "logs" / "computer.jsonl"


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in args.items():
        text = str(val)
        if key == "content" and len(text) > 200:
            out[key] = text[:200] + "…"
        elif len(text) > 500:
            out[key] = text[:500] + "…"
        else:
            out[key] = val
    return out


def log_action(
    user_id: int,
    tool: str,
    tier: str,
    args: dict[str, Any],
    result: str,
    *,
    confirmed: bool,
) -> None:
    JsonlLog(_log_path()).append(
        {
            "ts": int(time.time()),
            "user_id": int(user_id),
            "tool": tool,
            "tier": tier,
            "args": _safe_args(args),
            "result_preview": (result or "")[:500],
            "confirmed": confirmed,
        }
    )


def tail_actions(*, limit: int = 10) -> list[dict[str, Any]]:
    p = _log_path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit * 2 :]):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                out.append(rec)
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out
