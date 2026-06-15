"""Клієнт host-agent: PowerShell, CLI, FS на Windows-хості."""
from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from .computer_confirm import wrap_execute
from .config import settings
from .ps_whitelist import check_ps_whitelist

logger = logging.getLogger("jarvis.tools.computer")

_TOKEN_HEADER = "X-Hostagent-Token"


def _enabled() -> bool:
    return settings.enable_computer_use and bool(settings.hostagent_token)


async def hostagent_healthy() -> bool:
    if not _enabled():
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as cli:
            resp = await cli.get(
                f"{settings.hostagent_url.rstrip('/')}/health",
                headers=_headers(),
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


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


def _check_cli_whitelist(exe: str, *, trusted: bool = False) -> str | None:
    if trusted:
        return None
    from .computer_learned import cli_exe_name, effective_cli_allowed

    allowed = effective_cli_allowed()
    if not allowed:
        return "CLI вимкнено: CLI_WHITELIST порожній і ще немає навчених exe."
    name = cli_exe_name(exe)
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


async def _run_powershell_impl(
    script: str, as_admin: bool = False, *, trusted: bool = False
) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    if as_admin and not settings.computer_allow_admin:
        return "Admin PowerShell вимкнено (COMPUTER_ALLOW_ADMIN=false)."
    err = check_ps_whitelist(script, trusted=trusted)
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


async def _run_cli_impl(
    exe: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    *,
    trusted: bool = False,
) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    err = _check_cli_whitelist(exe, trusted=trusted)
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


async def _capture_screenshot_impl() -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    data = await _request("POST", "/screen/capture")
    if "error" in data:
        return str(data["error"])
    raw = data.get("data_b64")
    if not raw:
        return "hostagent: порожня відповідь скріншота"
    try:
        png = base64.b64decode(str(raw), validate=True)
    except (ValueError, TypeError) as exc:
        return f"скріншот: невалідний base64 ({exc})"
    uploads = Path(settings.data_dir) / "uploads"
    try:
        uploads.mkdir(parents=True, exist_ok=True)
        dest = uploads / f"screenshot_{uuid.uuid4().hex[:10]}.png"
        dest.write_bytes(png)
    except OSError as exc:
        return f"не вдалося зберегти скріншот: {exc}"
    # Директива для gateway outbound — надішле фото в Telegram.
    return f"Скріншот знято (T0). [[photo:{dest.as_posix()}|екран]]"


async def _fs_write_impl(path: str, content: str) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    data = await _request("POST", "/fs/write", json={"path": path, "content": content})
    if "error" in data:
        return str(data["error"])
    return f"Записано: {data.get('path', path)} ✅"


async def _code_edit_impl(
    path: str,
    *,
    mode: str = "search_replace",
    old_string: str = "",
    new_string: str = "",
    diff: str = "",
    replace_all: bool = False,
) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    payload = {
        "path": path,
        "mode": mode,
        "old_string": old_string,
        "new_string": new_string,
        "diff": diff,
        "replace_all": replace_all,
    }
    data = await _request("POST", "/fs/edit", json=payload)
    if "error" in data:
        return str(data["error"])
    occ = data.get("occurrences", 1)
    backup = data.get("backup", "")
    preview = str(data.get("diff", "")).strip()
    head = f"Правку застосовано: {data.get('path', path)} (×{occ}) ✅"
    parts = [head]
    if preview:
        parts.append(f"```diff\n{preview}\n```")
    if backup:
        parts.append(f"backup: {backup}")
    return _truncate("\n".join(parts))


def _normalize_edits(edits: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(edits, list):
        return out
    for e in edits:
        if not isinstance(e, dict):
            continue
        out.append({
            "path": str(e.get("path", "")),
            "mode": str(e.get("mode", "search_replace")),
            "old_string": str(e.get("old_string", "")),
            "new_string": str(e.get("new_string", "")),
            "diff": str(e.get("diff", "")),
            "replace_all": bool(e.get("replace_all", False)),
        })
    return out


async def _code_edit_batch_impl(edits: Any, *, dry_run: bool = False) -> str:
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    norm = _normalize_edits(edits)
    if not norm:
        return "code_edit_batch: порожній або некоректний список edits."
    data = await _request(
        "POST", "/fs/edit_batch", json={"edits": norm, "dry_run": dry_run}
    )
    if "error" in data:
        return str(data["error"])
    results = data.get("results") or []
    dry = data.get("status") == "dry_run"
    head = (
        f"Dry-run: {len(results)} файл(ів) — diff без застосування 👀"
        if dry
        else f"Транзакційно застосовано {data.get('count', len(results))} файл(ів) ✅"
    )
    parts = [head]
    for r in results:
        if not isinstance(r, dict):
            continue
        block = f"• {r.get('path', '?')} (×{r.get('occurrences', 1)})"
        preview = str(r.get("diff", "")).strip()
        if preview:
            block += f"\n```diff\n{preview}\n```"
        backup = r.get("backup")
        if backup and not dry:
            block += f"\nbackup: {backup}"
        parts.append(block)
    return _truncate("\n".join(parts))


async def execute_internal(tool: str, args: dict[str, Any], *, trusted: bool = False) -> str:
    """Виконує computer-дію. trusted=True після ✅ у Telegram."""
    if tool == "run_powershell":
        return await _run_powershell_impl(
            str(args.get("script", "")),
            bool(args.get("as_admin", False)),
            trusted=trusted,
        )
    if tool == "run_cli":
        raw_args = args.get("args", [])
        cli_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        cwd = str(args.get("cwd", "")) or None
        return await _run_cli_impl(
            str(args.get("exe", "")), cli_args, cwd, trusted=trusted
        )
    if tool == "fs_list":
        return await _fs_list_impl(str(args.get("path", "")))
    if tool == "fs_read":
        return await _fs_read_impl(str(args.get("path", "")))
    if tool == "fs_write":
        return await _fs_write_impl(str(args.get("path", "")), str(args.get("content", "")))
    if tool == "code_edit":
        return await _code_edit_impl(
            str(args.get("path", "")),
            mode=str(args.get("mode", "search_replace")),
            old_string=str(args.get("old_string", "")),
            new_string=str(args.get("new_string", "")),
            diff=str(args.get("diff", "")),
            replace_all=bool(args.get("replace_all", False)),
        )
    if tool == "code_edit_batch":
        return await _code_edit_batch_impl(
            args.get("edits"), dry_run=bool(args.get("dry_run", False))
        )
    if tool == "capture_screenshot":
        return await _capture_screenshot_impl()
    if tool == "clipboard_write":
        return await _clipboard_write_impl(str(args.get("text", "")))
    if tool == "clipboard_read":
        return await _clipboard_read_impl()
    if tool == "window_list":
        return await _window_list_impl()
    if tool == "window_focus":
        return await _window_focus_impl(str(args.get("title", "")))
    if tool == "uia_invoke":
        return await _uia_invoke_impl(
            str(args.get("window", "")),
            str(args.get("control_name", "")),
            str(args.get("action", "click")),
        )
    if tool == "browser_open":
        from . import browser

        return await browser.browser_open(str(args.get("url", "")))
    if tool == "browser_read":
        from . import browser

        return await browser.browser_read()
    if tool == "browser_click":
        from . import browser

        return await browser.browser_click(str(args.get("selector", "")))
    if tool == "browser_fill":
        from . import browser

        return await browser.browser_fill(
            str(args.get("selector", "")), str(args.get("value", ""))
        )
    if tool == "browser_eval":
        from . import browser

        return await browser.browser_eval(str(args.get("js", "")))
    if tool == "screen_click":
        try:
            x = int(args.get("x", 0))
            y = int(args.get("y", 0))
        except (TypeError, ValueError):
            return "invalid coordinates"
        return await _screen_click_impl(x, y)
    if tool == "screen_type":
        return await _screen_type_impl(
            str(args.get("text", "")),
            int(args.get("interval_ms", 0) or 0),
        )
    if tool == "screen_hotkey":
        raw = args.get("keys", [])
        keys = [str(k) for k in raw] if isinstance(raw, list) else []
        return await _screen_hotkey_impl(keys)
    if tool == "screen_scroll":
        try:
            clicks = int(args.get("clicks", 0))
        except (TypeError, ValueError):
            return "invalid clicks"
        xv = args.get("x")
        yv = args.get("y")
        xi = int(xv) if xv is not None else None
        yi = int(yv) if yv is not None else None
        return await _screen_scroll_impl(clicks, xi, yi)
    if tool == "fs_write_bytes":
        raw = args.get("data_b64", "")
        try:
            data = base64.b64decode(str(raw), validate=True)
        except (ValueError, TypeError):
            return "invalid base64"
        code, _, err = await _request_raw(
            "POST",
            "/fs/write_bytes",
            json={"path": str(args.get("path", "")), "data_b64": str(raw)},
        )
        return err or f"Записано: {args.get('path')} ({len(data)} байт) ✅"
    return f"Невідома computer-дія: {tool}"


async def run_powershell(script: str, as_admin: bool = False, *, user_id: int = 0) -> str:
    if as_admin:
        from .computer_access import admin_powershell_denied_message

        denied = admin_powershell_denied_message(user_id)
        if denied:
            return denied
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


async def code_edit(
    path: str,
    *,
    mode: str = "search_replace",
    old_string: str = "",
    new_string: str = "",
    diff: str = "",
    replace_all: bool = False,
    user_id: int = 0,
) -> str:
    args = {
        "path": path,
        "mode": mode,
        "old_string": old_string,
        "new_string": new_string,
        "diff": diff,
        "replace_all": replace_all,
    }
    return await wrap_execute(
        user_id,
        "code_edit",
        args,
        lambda: _code_edit_impl(
            path,
            mode=mode,
            old_string=old_string,
            new_string=new_string,
            diff=diff,
            replace_all=replace_all,
        ),
    )


async def code_edit_batch(
    edits: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    user_id: int = 0,
) -> str:
    """Транзакційна multi-file правка (CA-4.3): усе або відкат; dry_run — лише diff (CA-4.4)."""
    args: dict[str, Any] = {"edits": edits, "dry_run": dry_run}
    return await wrap_execute(
        user_id,
        "code_edit_batch",
        args,
        lambda: _code_edit_batch_impl(edits, dry_run=dry_run),
    )


async def _request_raw(method: str, path: str, **kwargs: Any) -> tuple[int, bytes, str]:
    """HTTP → (status, body, error)."""
    if not _enabled():
        return 0, b"", "Computer Use вимкнено."
    url = f"{settings.hostagent_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.computer_timeout) as cli:
            resp = await cli.request(method, url, headers=_headers(), **kwargs)
            if resp.status_code >= 400:
                return resp.status_code, b"", resp.text[:300]
            return resp.status_code, resp.content, ""
    except httpx.HTTPError as exc:
        return 0, b"", f"hostagent недоступний: {exc}"


async def download_file(path: str, *, user_id: int = 0) -> tuple[bytes, str, str]:
    """Повертає (bytes, filename, error)."""
    from .computer_access import computer_denied_message

    denied = computer_denied_message(user_id)
    if denied:
        return b"", "", denied
    code, data, err = await _request_raw("GET", "/fs/download", params={"path": path})
    if err:
        return b"", "", err
    name = Path(path).name or "file.bin"
    return data, name, ""


async def upload_file_bytes(path: str, data: bytes, *, user_id: int = 0) -> str:
    args = {"path": path, "size": len(data)}
    b64 = base64.b64encode(data).decode("ascii")

    async def _do() -> str:
        code, _, err = await _request_raw(
            "POST", "/fs/write_bytes", json={"path": path, "data_b64": b64}
        )
        if err:
            return err
        return f"Записано на хост: {path} ({len(data)} байт) ✅"

    return await wrap_execute(user_id, "fs_write_bytes", args, _do)


async def _clipboard_read_impl() -> str:
    data = await _request("GET", "/clipboard")
    if "error" in data:
        return str(data["error"])
    text = str(data.get("text", ""))
    return _truncate(f"Буфер обміну:\n{text or '(порожньо)'}")


async def _clipboard_write_impl(text: str) -> str:
    data = await _request("POST", "/clipboard", json={"text": text})
    if "error" in data:
        return str(data["error"])
    return "Буфер обміну оновлено ✅"


async def clipboard_read(*, user_id: int = 0) -> str:
    return await wrap_execute(
        user_id, "clipboard_read", {}, lambda: _clipboard_read_impl()
    )


async def clipboard_write(text: str, *, user_id: int = 0) -> str:
    return await wrap_execute(
        user_id,
        "clipboard_write",
        {"text": text[:2000]},
        lambda: _clipboard_write_impl(text),
    )


async def capture_screenshot(*, user_id: int = 0) -> str:
    return await wrap_execute(
        user_id, "capture_screenshot", {}, lambda: _capture_screenshot_impl()
    )


async def see_screen(question: str = "", *, user_id: int = 0) -> str:
    """Smart screen: screenshot → vision (якщо увімкнено)."""
    shot = await capture_screenshot(user_id=user_id)
    if "[[photo:" not in shot:
        return shot
    import re

    m = re.search(r"\[\[photo:([^|\]]+)", shot)
    if not m or not settings.computer_auto_vision or not settings.ollama_model_vision:
        return shot
    from .toolkit import describe_image

    path = m.group(1).strip()
    q = question.strip() or "Опиши що на екрані, зокрема помилки та важливі елементи UI."
    desc = await describe_image(path, q)
    return f"{shot}\n\n👁 Vision:\n{desc}"


async def _window_list_impl() -> str:
    data = await _request("GET", "/window/list")
    if "error" in data:
        return str(data["error"])
    windows = data.get("windows") or []
    if not windows:
        return "Відкритих вікон з заголовком не знайдено."
    lines = []
    for w in windows[:40]:
        if isinstance(w, dict):
            lines.append(
                f"- {w.get('ProcessName', '?')}: {w.get('MainWindowTitle', '')[:80]}"
            )
    return _truncate("Вікна:\n" + "\n".join(lines))


async def _window_focus_impl(title: str) -> str:
    data = await _request("POST", "/window/focus", params={"title": title})
    if "error" in data:
        return str(data["error"])
    return f"Фокус: {data.get('title', title)} ✅"


async def _uia_invoke_impl(window: str, control_name: str, action: str) -> str:
    data = await _request(
        "POST",
        "/uia/invoke",
        json={"window": window, "control_name": control_name, "action": action},
    )
    if "error" in data:
        return str(data["error"])
    return f"UIA: {control_name} ({action}) ✅"


async def window_list(*, user_id: int = 0) -> str:
    return await wrap_execute(user_id, "window_list", {}, lambda: _window_list_impl())


async def window_focus(title: str, *, user_id: int = 0) -> str:
    args = {"title": title}
    return await wrap_execute(
        user_id, "window_focus", args, lambda: _window_focus_impl(title)
    )


async def _screen_click_impl(x: int, y: int) -> str:
    data = await _request("POST", "/screen/click", json={"x": x, "y": y})
    if "error" in data:
        return str(data["error"])
    return f"Клік ({x}, {y}) ✅"


async def screen_click(x: int, y: int, *, user_id: int = 0) -> str:
    args = {"x": x, "y": y}
    return await wrap_execute(
        user_id, "screen_click", args, lambda: _screen_click_impl(x, y)
    )


async def _screen_type_impl(text: str, interval_ms: int = 0) -> str:
    data = await _request(
        "POST",
        "/screen/type",
        json={"text": text, "interval_ms": interval_ms},
    )
    if "error" in data:
        return str(data["error"])
    return f"Введено {data.get('chars', len(text))} символів ✅"


async def screen_type(text: str, interval_ms: int = 0, *, user_id: int = 0) -> str:
    args = {"text": text[:4000], "interval_ms": interval_ms}
    return await wrap_execute(
        user_id,
        "screen_type",
        args,
        lambda: _screen_type_impl(text[:4000], interval_ms),
    )


async def _screen_hotkey_impl(keys: list[str]) -> str:
    data = await _request("POST", "/screen/hotkey", json={"keys": keys})
    if "error" in data:
        return str(data["error"])
    return f"Hotkey {data.get('keys', '+'.join(keys))} ✅"


async def screen_hotkey(keys: list[str], *, user_id: int = 0) -> str:
    args = {"keys": keys}
    return await wrap_execute(
        user_id, "screen_hotkey", args, lambda: _screen_hotkey_impl(keys)
    )


async def _screen_scroll_impl(clicks: int, x: int | None, y: int | None) -> str:
    body: dict[str, Any] = {"clicks": clicks}
    if x is not None and y is not None:
        body["x"] = x
        body["y"] = y
    data = await _request("POST", "/screen/scroll", json=body)
    if "error" in data:
        return str(data["error"])
    return f"Scroll {clicks} ✅"


async def screen_scroll(
    clicks: int, x: int | None = None, y: int | None = None, *, user_id: int = 0
) -> str:
    args: dict[str, Any] = {"clicks": clicks}
    if x is not None and y is not None:
        args["x"] = x
        args["y"] = y
    return await wrap_execute(
        user_id,
        "screen_scroll",
        args,
        lambda: _screen_scroll_impl(clicks, x, y),
    )


async def uia_invoke(
    window: str, control_name: str, action: str = "click", *, user_id: int = 0
) -> str:
    args = {"window": window, "control_name": control_name, "action": action}
    return await wrap_execute(
        user_id,
        "uia_invoke",
        args,
        lambda: _uia_invoke_impl(window, control_name, action),
    )


async def power_action(action: str, delay_seconds: int = 60, *, user_id: int = 0) -> str:
    if not settings.computer_allow_power:
        return "Power actions вимкнено (COMPUTER_ALLOW_POWER=false)."

    async def _do() -> str:
        data = await _request(
            "POST",
            "/power",
            json={"action": action, "delay_seconds": delay_seconds},
        )
        if "error" in data:
            return str(data["error"])
        return f"Power {action} заплановано (delay={delay_seconds}s) ✅"

    return await wrap_execute(
        user_id,
        "power_action",
        {"action": action, "delay_seconds": delay_seconds},
        _do,
    )
