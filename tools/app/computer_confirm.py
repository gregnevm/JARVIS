"""Підтвердження мутуючих Computer Use дій через Redis (спільний із gateway)."""
from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from .computer_audit import log_action
from .computer_learned import is_cli_trusted, is_ps_trusted, learn_from_action
from .ps_whitelist import check_ps_whitelist, extract_ps_cmdlets
from .computer_access import computer_denied_message
from .config import settings
from .redis_util import get_redis

_PENDING_PREFIX = "jarvis:computer:pending:"
_ORIGIN_PREFIX = "jarvis:computer:origin:"
_PENDING_TTL = 300

CONFIRM_MARKER = "[[COMPUTER_CONFIRM:{code}]]"
ADMIN_CONFIRM_MARKER = "[[COMPUTER_ADMIN_CONFIRM:{code}]]"

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
    "fs_write_bytes": "T0",
    "code_edit": "T1",
    "code_edit_batch": "T1",
    "capture_screenshot": "T0",
    "clipboard_read": "T0",
    "clipboard_write": "T0",
    "run_cli": "T1",
    "power_action": "T0",
    "browser_open": "T2",
    "browser_read": "T2",
    "browser_click": "T2",
    "browser_fill": "T2",
    "browser_eval": "T2",
    "window_list": "T3",
    "window_focus": "T3",
    "uia_invoke": "T3",
    "screen_click": "T4",
    "screen_type": "T4",
    "screen_hotkey": "T4",
    "screen_scroll": "T4",
    "see_screen": "T0",
}


def _redis_str(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def _pending_key(user_id: int) -> str:
    return f"{_PENDING_PREFIX}{int(user_id)}"


def _origin_key(user_id: int) -> str:
    return f"{_ORIGIN_PREFIX}{int(user_id)}"


def tier_for(tool: str) -> str:
    return _TIER.get(tool, "T0")


def audit_tier(tool: str, args: dict[str, Any]) -> str:
    if tool == "run_powershell" and bool(args.get("as_admin")):
        return "admin"
    return tier_for(tool)


def _needs_admin_second_confirm(tool: str, args: dict[str, Any], data: dict[str, Any]) -> bool:
    return (
        tool == "run_powershell"
        and bool(args.get("as_admin"))
        and settings.computer_allow_admin
        and not bool(data.get("admin_armed"))
    )


def is_mutating(tool: str, args: dict[str, Any]) -> bool:
    if tool in (
        "fs_list",
        "fs_read",
        "capture_screenshot",
        "see_screen",
        "clipboard_read",
        "browser_open",
        "browser_read",
        "browser_eval",
    ):
        return False
    if tool in (
        "browser_click",
        "browser_fill",
        "window_focus",
        "uia_invoke",
        "screen_click",
        "screen_type",
        "screen_hotkey",
        "screen_scroll",
    ):
        return True
    if tool == "fs_write" or tool == "fs_write_bytes":
        return True
    if tool == "code_edit":
        return True
    if tool == "code_edit_batch":
        # dry_run нічого не пише → читання, без confirm.
        return not bool(args.get("dry_run", False))
    if tool == "clipboard_write":
        return True
    if tool == "power_action":
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
    if tool == "code_edit":
        path = args.get("path", "")
        mode = str(args.get("mode", "search_replace"))
        if mode == "diff":
            return f"code_edit {path} [diff]:\n{str(args.get('diff', ''))[:300]}"
        old = str(args.get("old_string", ""))[:120]
        new = str(args.get("new_string", ""))[:120]
        scope = " [усі збіги]" if args.get("replace_all") else ""
        return f"code_edit {path}{scope}:\n- {old}\n+ {new}"
    if tool == "code_edit_batch":
        raw = args.get("edits") or []
        paths = [str(e.get("path", "")) for e in raw if isinstance(e, dict)]
        shown = ", ".join(paths[:5]) + ("…" if len(paths) > 5 else "")
        dry = " [dry-run]" if args.get("dry_run") else ""
        return f"code_edit_batch{dry}: {len(paths)} файл(ів) транзакційно: {shown}"
    if tool == "browser_click":
        return f"Browser click: {args.get('selector', '')}"
    if tool == "browser_fill":
        return f"Browser fill {args.get('selector', '')}: {str(args.get('value', ''))[:80]}"
    if tool == "browser_open":
        return f"Browser open: {args.get('url', '')}"
    if tool == "window_focus":
        return f"Window focus: {args.get('title', '')}"
    if tool == "uia_invoke":
        return f"UIA {args.get('action', 'click')}: {args.get('control_name', '')}"
    return f"{tool}: {args}"


async def save_pending(
    user_id: int,
    tool: str,
    args: dict[str, Any],
    *,
    admin_armed: bool = False,
) -> str:
    code = secrets.token_hex(3)
    payload = json.dumps(
        {
            "tool": tool,
            "args": args,
            "tier": audit_tier(tool, args),
            "admin_armed": admin_armed,
        },
        ensure_ascii=False,
    )
    await get_redis().setex(_pending_key(user_id), _PENDING_TTL, f"{code}:{payload}")
    return code


async def load_pending(user_id: int, code: str) -> dict[str, Any] | None:
    raw = await get_redis().get(_pending_key(user_id))
    if not raw:
        return None
    stored_code, _, payload = _redis_str(raw).partition(":")
    if stored_code != code.lower().strip():
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def clear_pending(user_id: int) -> None:
    await get_redis().delete(_pending_key(user_id))
    await clear_origin(user_id)


async def save_origin(user_id: int, text: str) -> None:
    """Зберігає оригінальний user prompt для resume після confirm."""
    t = (text or "").strip()
    if not t or int(user_id) <= 0:
        return
    await get_redis().setex(_origin_key(user_id), _PENDING_TTL, t[:4000])


async def load_origin(user_id: int) -> str:
    raw = await get_redis().get(_origin_key(user_id))
    return _redis_str(raw).strip()


async def clear_origin(user_id: int) -> None:
    await get_redis().delete(_origin_key(user_id))


async def load_pending_raw(user_id: int) -> dict[str, Any]:
    """Для Mini App — поточний pending з повним описом дії."""
    raw = await get_redis().get(_pending_key(user_id))
    if not raw:
        return {"pending": False}
    stored_code, _, payload = _redis_str(raw).partition(":")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    tool = str(data.get("tool") or "")
    raw_args = data.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    return {
        "pending": True,
        "code": stored_code,
        "tool": tool,
        "tier": data.get("tier") if isinstance(data, dict) else "",
        "script": str(args.get("script", "")) if tool == "run_powershell" else "",
        "description": describe_action(tool, args) if tool else "",
        "mutating": is_mutating(tool, args) if tool else False,
        "as_admin": bool(args.get("as_admin")),
    }


def _trust_skips_confirm(tool: str, args: dict[str, Any], level: str | None) -> bool:
    if not level or bool(args.get("as_admin")):
        return False
    if not is_mutating(tool, args):
        return False
    if level == "full":
        return True
    return tier_for(tool) in ("T0", "T1")


async def _is_effectively_mutating(
    tool: str, args: dict[str, Any], *, user_id: int
) -> bool:
    from .computer_trust import trust_level

    mutating = is_mutating(tool, args)
    if bool(args.get("as_admin")):
        return True
    if not mutating:
        return False
    level = await trust_level(user_id)
    if _trust_skips_confirm(tool, args, level):
        return False
    return True


async def _check_mutating_quota(user_id: int, tool: str, args: dict[str, Any]) -> str | None:
    from .computer_rate_limit import check_mutating_allowed

    if not (is_mutating(tool, args) or bool(args.get("as_admin"))):
        return None
    return await check_mutating_allowed(user_id)


async def _touch_mutating_quota(user_id: int, tool: str, args: dict[str, Any]) -> None:
    from .computer_rate_limit import record_mutating

    if is_mutating(tool, args) or bool(args.get("as_admin")):
        await record_mutating(user_id)


async def wrap_execute(
    user_id: int,
    tool: str,
    args: dict[str, Any],
    executor: Callable[[], Awaitable[str]],
) -> str:
    """Виконує дію або повертає маркер підтвердження для gateway."""
    denied = computer_denied_message(user_id)
    if denied:
        return denied
    tier = audit_tier(tool, args)
    mutating = await _is_effectively_mutating(tool, args, user_id=user_id)
    if mutating:
        blocked = await _check_mutating_quota(user_id, tool, args)
        if blocked:
            return blocked
    if mutating and settings.computer_require_confirm and int(user_id) > 0:
        await _touch_mutating_quota(user_id, tool, args)
        code = await save_pending(user_id, tool, args)
        desc = describe_action(tool, args)
        log_action(user_id, tool, tier, args, f"pending confirm {code}", confirmed=False)
        return CONFIRM_MARKER.format(code=code) + f" {desc}"
    result = await executor()
    if mutating:
        await _touch_mutating_quota(user_id, tool, args)
    log_action(user_id, tool, tier, args, result, confirmed=not mutating)
    return result


async def execute_confirmed(user_id: int, code: str) -> tuple[str, str]:
    from . import computer as comp
    from .computer_access import admin_powershell_denied_message

    denied = computer_denied_message(user_id)
    if denied:
        return denied, ""
    data = await load_pending(user_id, code)
    if not data:
        return "Дію прострочено або код невірний.", ""
    origin = await load_origin(user_id)
    tool = str(data.get("tool", ""))
    raw_args = data.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    tier = str(data.get("tier") or audit_tier(tool, args))

    if _needs_admin_second_confirm(tool, args, data):
        admin_denied = admin_powershell_denied_message(user_id)
        if admin_denied:
            await clear_pending(user_id)
            return admin_denied, origin
        code2 = await save_pending(user_id, tool, args, admin_armed=True)
        desc = describe_action(tool, args)
        log_action(
            user_id,
            tool,
            "admin",
            args,
            f"pending admin confirm {code2}",
            confirmed=False,
        )
        return (
            ADMIN_CONFIRM_MARKER.format(code=code2)
            + f" ⚠️ Друге підтвердження Admin PowerShell: {desc}",
            origin,
        )

    await clear_pending(user_id)
    blocked = await _check_mutating_quota(user_id, tool, args)
    if blocked:
        return blocked, origin
    result = await comp.execute_internal(tool, args, trusted=True)
    await _touch_mutating_quota(user_id, tool, args)
    learn_from_action(tool, args)
    log_action(user_id, tool, tier, args, result, confirmed=True)
    from .computer_trust import grant_trust, trust_ttl_seconds

    if trust_ttl_seconds() > 0:
        await grant_trust(user_id)
    return result, origin
