"""Клієнт host-agent: PowerShell, CLI, FS на Windows-хості."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .computer_confirm import wrap_execute
from .config import settings

logger = logging.getLogger("jarvis.tools.computer")

_TOKEN_HEADER = "X-Hostagent-Token"


def _enabled() -> bool:
    return settings.enable_computer_use and bool(settings.hostagent_token)


def _headers() -> dict[str, str]:
    return {_TOKEN_HEADER: settings.hostagent_token}


def _truncate(text: str) -> str:
    limit = settings.fetch_max_chars
    if len(text) <= limit:
        return text
    return text[:limit] + " …[обрізано]"


def _format_exec(stdout: str, stderr: str, code: int) -> str:
    parts: list[str] = []
    if stdout.strip():
        parts.append(stdout.strip())
    if stderr.strip():
        parts.append(f"[stderr] {stderr.strip()}")
    parts.append(f"[exit {code}]")
    return _truncate("\n".join(parts))


def _parse_whitelist(raw: str) -> set[str]:
    return {x.strip().lower() for x in (raw or "").split(",") if x.strip()}


def _check_ps_whitelist(script: str) -> str | None:
    allowed = _parse_whitelist(settings.ps_whitelist)
    if not allowed:
        return "PowerShell вимкнено: PS_WHITELIST порожній."
    first = (script or "").strip().split(None, 1)[0].lower().rstrip(";")
    if first not in allowed:
        return f"PowerShell-команда '{first}' не в PS_WHITELIST."
    return None


def _check_cli_whitelist(exe: str) -> str | None:
    allowed = _parse_whitelist(settings.cli_whitelist)
    if not allowed:
        return "CLI вимкнено: CLI_WHITELIST порожній."
    name = (exe or "").strip().split("\\")[-1].split("/")[-1].lower()
    if name not in allowed:
        return f"CLI '{name}' не в CLI_WHITELIST."
    return None


async def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    if not _enabled():
        return {"error": "Computer Use вимкнено (ENABLE_COMPUTER_USE=false або немає HOSTAGENT_TOKEN)."}
    url = f"{settings.hostagent_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.computer_timeout) as cli:
            resp = await cli.request(method, url, headers=_headers(), **kwargs)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "invalid response"}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:200] if exc.response else str(exc)
        return {"error": f"hostagent HTTP {exc.response.status_code}: {detail}"}
    except httpx.HTTPError as exc:
        logger.error("hostagent request failed: %s", exc)
        return {"error": f"hostagent недоступний: {exc}"}


async def _run_powershell_impl(script: str, as_admin: bool = False) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    if as_admin and not settings.computer_allow_admin:
        return "Admin PowerShell вимкнено (COMPUTER_ALLOW_ADMIN=false)."
    err = _check_ps_whitelist(script)
    if err:
        return err
    data = await _request(
        "POST",
        "/powershell",
        json={"script": script, "as_admin": as_admin},
    )
    if "error" in data:
        return str(data["error"])
    return _format_exec(
        str(data.get("stdout", "")),
        str(data.get("stderr", "")),
        int(data.get("code", -1)),
    )


async def _run_cli_impl(exe: str, args: list[str] | None = None, cwd: str | None = None) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    err = _check_cli_whitelist(exe)
    if err:
        return err
    data = await _request(
        "POST",
        "/cli",
        json={"exe": exe, "args": args or [], "cwd": cwd},
    )
    if "error" in data:
        return str(data["error"])
    return _format_exec(
        str(data.get("stdout", "")),
        str(data.get("stderr", "")),
        int(data.get("code", -1)),
    )


async def _fs_list_impl(path: str) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    data = await _request("GET", "/fs/list", params={"path": path})
    if "error" in data:
        return str(data["error"])
    entries = data.get("entries") or []
    lines = [f"{e.get('kind', '?')}: {e.get('name', '?')}" for e in entries]
    header = f"Каталог {data.get('path', path)} ({len(lines)} елементів)"
    body = "\n".join(lines[:200]) if lines else "(порожньо)"
    return _truncate(f"{header}\n{body}")


async def _fs_read_impl(path: str) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    data = await _request("GET", "/fs/read", params={"path": path})
    if "error" in data:
        return str(data["error"])
    content = str(data.get("content", ""))
    note = " [обрізано]" if data.get("truncated") else ""
    return _truncate(f"Файл {data.get('path', path)}{note}:\n{content}")


async def _fs_write_impl(path: str, content: str) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    data = await _request("POST", "/fs/write", json={"path": path, "content": content})
    if "error" in data:
        return str(data["error"])
    return f"Записано: {data.get('path', path)} ✅"


async def execute_internal(tool: str, args: dict[str, Any]) -> str:
    """Виконує computer-дію без перевірки підтвердження (після ✅ у Telegram)."""
    if tool == "run_powershell":
        return await _run_powershell_impl(
            str(args.get("script", "")),
            bool(args.get("as_admin", False)),
        )
    if tool == "run_cli":
        raw_args = args.get("args", [])
        cli_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        cwd = str(args.get("cwd", "")) or None
        return await _run_cli_impl(str(args.get("exe", "")), cli_args, cwd)
    if tool == "fs_list":
        return await _fs_list_impl(str(args.get("path", "")))
    if tool == "fs_read":
        return await _fs_read_impl(str(args.get("path", "")))
    if tool == "fs_write":
        return await _fs_write_impl(str(args.get("path", "")), str(args.get("content", "")))
    return f"Невідома computer-дія: {tool}"


async def run_powershell(script: str, as_admin: bool = False, *, user_id: int = 0) -> str:
    args = {"script": script, "as_admin": as_admin}
    return await wrap_execute(
        user_id,
        "run_powershell",
        args,
        lambda: _run_powershell_impl(script, as_admin),
    )


async def run_cli(
    exe: str, args: list[str] | None = None, cwd: str | None = None, *, user_id: int = 0
) -> str:
    payload = {"exe": exe, "args": args or [], "cwd": cwd}
    return await wrap_execute(
        user_id,
        "run_cli",
        payload,
        lambda: _run_cli_impl(exe, args, cwd),
    )


async def fs_list(path: str, *, user_id: int = 0) -> str:
    return await wrap_execute(user_id, "fs_list", {"path": path}, lambda: _fs_list_impl(path))


async def fs_read(path: str, *, user_id: int = 0) -> str:
    return await wrap_execute(user_id, "fs_read", {"path": path}, lambda: _fs_read_impl(path))


async def fs_write(path: str, content: str, *, user_id: int = 0) -> str:
    args = {"path": path, "content": content}
    return await wrap_execute(user_id, "fs_write", args, lambda: _fs_write_impl(path, content))
