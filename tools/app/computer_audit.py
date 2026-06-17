"""Аудит Computer Use → data/logs/computer.jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from jarvis_core.llm.jsonl_log import JsonlLog
from jarvis_core.passport import default_redactor

from .config import settings


def _log_path() -> Path:
    return Path(settings.data_dir) / "logs" / "computer.jsonl"


def _redact(text: str) -> str:
    """Бекстоп проти витоку секретів у computer.jsonl (токени/паролі/ключі в PS/CLI)."""
    return default_redactor().redact(text)


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in args.items():
        # Спершу редакція (str-значення), потім трункейт — секрети не лягають cleartext.
        val = _redact(val) if isinstance(val, str) else val
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
            "result_preview": _redact((result or "")[:500]),
            "confirmed": confirmed,
        }
    )


def tail_actions(*, limit: int = 10, tool: str | None = None) -> list[dict[str, Any]]:
    p = _log_path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    want = (tool or "").strip()
    scan = max(limit * 4, limit * 2) if want else limit * 2
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-scan:]):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                continue
            if want and str(rec.get("tool", "")) != want:
                continue
            out.append(rec)
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out
