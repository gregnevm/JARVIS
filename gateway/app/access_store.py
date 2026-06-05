"""Динамічний whitelist (друзі), погоджені через бота. Базовий список — ALLOWED_USER_IDS у .env."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.access_store")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class UserRecord:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


def record_from_telegram(user: dict[str, Any]) -> UserRecord:
    return UserRecord(
        user_id=int(user["id"]),
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )


def format_user_label(rec: UserRecord) -> str:
    parts: list[str] = []
    if rec.first_name:
        parts.append(str(rec.first_name))
    if rec.last_name:
        parts.append(str(rec.last_name))
    name = " ".join(parts).strip() or "—"
    uname = f"@{rec.username}" if rec.username else "без username"
    return f"{name} ({uname}, id <code>{rec.user_id}</code>)"


class AccessStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._approved: dict[int, dict[str, Any]] = {}
        self._pending: dict[int, dict[str, Any]] = {}

    @property
    def approved_ids(self) -> set[int]:
        return set(self._approved.keys())

    @property
    def pending_ids(self) -> set[int]:
        return set(self._pending.keys())

    def get_approved(self, user_id: int) -> dict[str, Any] | None:
        return self._approved.get(user_id)

    def get_pending(self, user_id: int) -> dict[str, Any] | None:
        return self._pending.get(user_id)

    def list_pending(self) -> list[UserRecord]:
        out: list[UserRecord] = []
        for raw in self._pending.values():
            out.append(
                UserRecord(
                    user_id=int(raw["user_id"]),
                    username=raw.get("username"),
                    first_name=raw.get("first_name"),
                    last_name=raw.get("last_name"),
                )
            )
        out.sort(key=lambda r: r.user_id)
        return out

    def list_approved(self) -> list[UserRecord]:
        out: list[UserRecord] = []
        for raw in self._approved.values():
            out.append(
                UserRecord(
                    user_id=int(raw["user_id"]),
                    username=raw.get("username"),
                    first_name=raw.get("first_name"),
                    last_name=raw.get("last_name"),
                )
            )
        out.sort(key=lambda r: r.user_id)
        return out

    async def load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("access store load failed: %s", exc)
            return
        async with self._lock:
            self._approved = {
                int(x["user_id"]): x for x in data.get("approved", []) if "user_id" in x
            }
            self._pending = {
                int(x["user_id"]): x for x in data.get("pending", []) if "user_id" in x
            }

    async def _persist(self) -> None:
        payload = {
            "approved": list(self._approved.values()),
            "pending": list(self._pending.values()),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    async def add_pending(self, rec: UserRecord) -> bool:
        """Додає в чергу. False — уже в approved або pending."""
        async with self._lock:
            if rec.user_id in self._approved or rec.user_id in self._pending:
                return False
            self._pending[rec.user_id] = {
                "user_id": rec.user_id,
                "username": rec.username,
                "first_name": rec.first_name,
                "last_name": rec.last_name,
                "requested_at": _utc_now(),
            }
            await self._persist()
        return True

    async def approve(self, user_id: int, *, by_admin: int) -> tuple[bool, str, UserRecord | None]:
        async with self._lock:
            pending = self._pending.pop(user_id, None)
            if pending:
                rec = UserRecord(
                    user_id=user_id,
                    username=pending.get("username"),
                    first_name=pending.get("first_name"),
                    last_name=pending.get("last_name"),
                )
            elif user_id in self._approved:
                return False, "Користувач уже має доступ.", None
            else:
                rec = UserRecord(user_id=user_id, username=None, first_name=None, last_name=None)

            self._approved[user_id] = {
                "user_id": user_id,
                "username": rec.username,
                "first_name": rec.first_name,
                "last_name": rec.last_name,
                "approved_at": _utc_now(),
                "approved_by": by_admin,
            }
            await self._persist()
        return True, "ok", rec

    async def deny(self, user_id: int) -> tuple[bool, str]:
        async with self._lock:
            if user_id not in self._pending:
                return False, "Немає такого запиту в черзі."
            del self._pending[user_id]
            await self._persist()
        return True, "ok"

    async def revoke(self, user_id: int) -> tuple[bool, str]:
        async with self._lock:
            if user_id not in self._approved:
                return False, "Користувач не в списку погоджених через бота."
            del self._approved[user_id]
            await self._persist()
        return True, "ok"
