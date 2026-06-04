"""Підтвердження мутуючих Computer Use дій через Redis (спільний із gateway)."""
from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis

from .computer_audit import log_action
from .computer_learned import is_cli_trusted, is_ps_trusted, learn_from_action
from .ps_whitelist import check_ps_whitelist, extract_ps_cmdlets
from .config import settings

_PENDING_PREFIX = "jarvis:computer:pending:"
_ORIGIN_PREFIX = "jarvis:computer:origin:"
_PENDING_TTL = 300

CONFIRM_MARKER = "[[COMPUTER_CONFIRM:{code}]]"

_READONLY_PS = frozenset(
    {
        "get-childitem",
        "get-content",
        "get-service",
        "get-process",
        "test-path",
        "write-output",
        "select-object",
        "format-table",
        "get-item",
        "get-location",
    }
)

_TIER = {
    "run_powershell": "T0",
    "fs_list": "T0",
    "fs_read": "T0",
    "fs_write": "T0",
    "capture_screenshot": "T0",
    "run_cli": "T1",
}

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def aclose_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _pending_key(user_id: int) -> str:
    return f"{_PENDING_PREFIX}{int(user_id)}"


def _origin_key(user_id: int) -> str:
    return f"{_ORIGIN_PREFIX}{int(user_id)}"


def tier_for(tool: str) -> str:
    return _TIER.get(tool, "T0")


def is_mutating(tool: str, args: dict[str, Any]) -> bool:
    if tool in ("fs_list", "fs_read", "capture_screenshot"):
        return False
    if tool == "fs_write":
        return True
    if tool == "run_cli":
        if is_cli_trusted(str(args.get("exe", ""))):
            return False
        return True
    if tool == "run_powershell":
        if bool(args.get("as_admin")):
            return True
        script = str(args.get("script", "")).strip()
        if not script:
            return False
        if is_ps_trusted(script):
            return False
        cmdlets = extract_ps_cmdlets(script)
        if not cmdlets:
            return False
        if check_ps_whitelist(script, trusted=False) is not None:
            if all(c in _READONLY_PS for c in cmdlets):
                return False
            return True
        return any(c not in _READONLY_PS for c in cmdlets)
    return False


def describe_action(tool: str, args: dict[str, Any]) -> str:
    if tool == "run_powershell":
        admin = " [admin]" if args.get("as_admin") else ""
        script = str(args.get("script", ""))[:200]
        return f"PowerShell{admin}: {script}"
    if tool == "run_cli":
        exe = args.get("exe", "")
        cli_args = args.get("args") or []
        return f"CLI: {exe} {' '.join(str(a) for a in cli_args)[:150]}"
    if tool == "fs_write":
        path = args.get("path", "")
        preview = str(args.get("content", ""))[:80]
        return f"Запис у файл {path}: {preview}…"
    return f"{tool}: {args}"


async def save_pending(user_id: int, tool: str, args: dict[str, Any]) -> str:
    code = secrets.token_hex(3)
    payload = json.dumps({"tool": tool, "args": args, "tier": tier_for(tool)}, ensure_ascii=False)
    await _client().setex(_pending_key(user_id), _PENDING_TTL, f"{code}:{payload}")
    return code


async def load_pending(user_id: int, code: str) -> dict[str, Any] | None:
    raw = await _client().get(_pending_key(user_id))
    if not raw:
        return None
    stored_code, _, payload = raw.partition(":")
    if stored_code != code.lower().strip():
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def clear_pending(user_id: int) -> None:
    await _client().delete(_pending_key(user_id))
    await clear_origin(user_id)


async def save_origin(user_id: int, text: str) -> None:
    """Зберігає оригінальний user prompt для resume після confirm."""
    t = (text or "").strip()
    if not t or int(user_id) <= 0:
        return
    await _client().setex(_origin_key(user_id), _PENDING_TTL, t[:4000])


async def load_origin(user_id: int) -> str:
    raw = await _client().get(_origin_key(user_id))
    return (raw or "").strip() if raw else ""


async def clear_origin(user_id: int) -> None:
    await _client().delete(_origin_key(user_id))


async def wrap_execute(
    user_id: int,
    tool: str,
    args: dict[str, Any],
    executor: Callable[[], Awaitable[str]],
) -> str:
    """Виконує дію або повертає маркер підтвердження для gateway."""
    tier = tier_for(tool)
    mutating = is_mutating(tool, args)
    if mutating and settings.computer_require_confirm and int(user_id) > 0:
        code = await save_pending(user_id, tool, args)
        desc = describe_action(tool, args)
        log_action(user_id, tool, tier, args, f"pending confirm {code}", confirmed=False)
        return CONFIRM_MARKER.format(code=code) + f" {desc}"
    result = await executor()
    log_action(user_id, tool, tier, args, result, confirmed=not mutating)
    return result


async def execute_confirmed(user_id: int, code: str) -> tuple[str, str]:
    from . import computer as comp

    data = await load_pending(user_id, code)
    if not data:
        return "Дію прострочено або код невірний.", ""
    origin = await load_origin(user_id)
    await clear_pending(user_id)
    tool = str(data.get("tool", ""))
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    tier = str(data.get("tier") or tier_for(tool))
    result = await comp.execute_internal(tool, args, trusted=True)
    learn_from_action(tool, args)
    log_action(user_id, tool, tier, args, result, confirmed=True)
    return result, origin
