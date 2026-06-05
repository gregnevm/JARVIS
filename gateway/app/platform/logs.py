"""P0.5 Logs — перегляд session-логів (data/logs/sessions/user_*.jsonl).

Ті самі JSONL, що пише tools/app/session_ingest.py: {ts,user_id,mode,iters,user,
assistant}. Фільтри: user_id, mode, limit. Time-to-debug < 2хв (KPI §7).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import settings
from .auth import PlatformAuth, require_platform_auth

logger = logging.getLogger("jarvis.gateway.platform.logs")


def _sessions_dir() -> Path:
    return Path(settings.data_dir) / "logs" / "sessions"


class _UserLog(BaseModel):
    user_id: int
    turns: int
    bytes: int


def _read_turns(path: Path, *, mode: str | None, limit: int) -> list[dict[str, Any]]:
    """Парсить JSONL, фільтрує за mode, повертає останні `limit` (новіші першими)."""
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if mode and str(rec.get("mode") or "").lower() != mode:
                    continue
                out.append(rec)
    except OSError as exc:
        logger.warning("read log %s failed: %s", path, exc)
        return []
    out.reverse()
    return out[:limit]


def register(router: APIRouter) -> None:
    @router.get("/platform/api/logs/users")
    async def logs_users(_auth: PlatformAuth = Depends(require_platform_auth)) -> dict[str, Any]:
        base = _sessions_dir()
        users: list[dict[str, Any]] = []
        if base.is_dir():
            for path in sorted(base.glob("user_*.jsonl")):
                try:
                    uid = int(path.stem.removeprefix("user_"))
                except ValueError:
                    continue
                try:
                    size = path.stat().st_size
                    turns = sum(1 for _ in path.open("r", encoding="utf-8"))
                except OSError:
                    size, turns = 0, 0
                users.append({"user_id": uid, "turns": turns, "bytes": size})
        users.sort(key=lambda u: -u["turns"])
        return {"users": users}

    @router.get("/platform/api/logs")
    async def logs_tail(
        _auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int = 0,
        mode: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        lim = max(1, min(limit, 200))
        norm_mode = (mode or "").strip().lower() or None
        path = _sessions_dir() / f"user_{int(user_id)}.jsonl"
        if int(user_id) <= 0 or not path.is_file():
            return {"turns": [], "user_id": int(user_id)}
        turns = _read_turns(path, mode=norm_mode, limit=lim)
        return {"turns": turns, "user_id": int(user_id), "mode": norm_mode}
