"""Аудит Computer Use → data/logs/computer.jsonl."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from jarvis_core.llm.jsonl_log import JsonlLog
from jarvis_core.passport import default_redactor

from .config import settings

# Інструменти, що виконуються на Windows-хості через hostagent — крос-нодові
# дії (Twin-контейнер → hostagent). Маркуємо їх окремим класом в аудиті
# (multi-node authority, `docs/COMPETITIVE_ANALYSIS.md` §3.10): у логу видно, що
# дія перетнула межу вузла, а не лишилась у пісочниці tools-контейнера.
_HOSTAGENT_TOOLS = frozenset(
    {
        "run_powershell", "run_cli",
        "fs_list", "fs_read", "fs_write", "fs_write_bytes",
        "capture_screenshot", "clipboard_read", "clipboard_write", "power_action",
        "window_list", "window_focus", "uia_invoke",
        "screen_click", "screen_type", "screen_hotkey", "screen_scroll", "see_screen",
        "browser_open", "browser_read", "browser_click", "browser_fill", "browser_eval",
    }
)


def execution_node(tool: str) -> str:
    """`hostagent` (крос-нодова дія на Windows-хості) | `local` (у tools-контейнері).

    Спостережуваність, не enforcement: невідомий інструмент → `local` (він не
    у hostagent-контракті, тож не перетинає межу вузла)."""
    return "hostagent" if tool in _HOSTAGENT_TOOLS else "local"


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
            "node": execution_node(tool),
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
