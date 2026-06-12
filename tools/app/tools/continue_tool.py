"""Continue.dev — VS Code + local agent API (cn serve / IDE extension)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("jarvis.tools.continue_dev")


def enabled() -> bool:
    return bool(settings.enable_continue_dev and settings.enable_computer_use)


def _api_base() -> str:
    return (settings.continue_dev_url or "http://host.docker.internal:65432").rstrip("/")


def _vscode_cli() -> str:
    return (settings.continue_vscode_cli or "code").strip() or "code"


def _history_len(state: dict[str, Any]) -> int:
    session = state.get("session")
    if isinstance(session, dict):
        history = session.get("history")
        if isinstance(history, list):
            return len(history)
    history = state.get("history")
    return len(history) if isinstance(history, list) else 0


def _last_assistant_text(state: dict[str, Any]) -> str:
    history: list[Any] = []
    session = state.get("session")
    if isinstance(session, dict) and isinstance(session.get("history"), list):
        history = session["history"]
    elif isinstance(state.get("history"), list):
        history = state["history"]

    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        msg = item.get("message") if isinstance(item.get("message"), dict) else item
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                str(p.get("text", ""))
                for p in content
                if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
            ]
            joined = "\n".join(parts).strip()
            if joined:
                return joined
    return ""


def _truncate(text: str) -> str:
    limit = settings.fetch_max_chars
    if len(text) <= limit:
        return text
    return text[:limit] + " …[обрізано]"


def _format_status(state: dict[str, Any]) -> str:
    processing = bool(state.get("isProcessing"))
    queue = state.get("queueLength", state.get("queue_length", "?"))
    pending = state.get("pendingPermission")
    reply = _last_assistant_text(state)
    lines = [
        f"isProcessing={processing}",
        f"queueLength={queue}",
        f"pendingPermission={'yes' if pending else 'no'}",
    ]
    if reply:
        lines.append(f"lastAssistant:\n{_truncate(reply)}")
    return "\n".join(lines)


async def run(
    action: str,
    *,
    path: str = "",
    prompt: str = "",
    user_id: int = 0,
) -> str:
    if not settings.enable_continue_dev:
        return "Continue.dev вимкнено (ENABLE_CONTINUE_DEV=false)."
    if not settings.enable_computer_use:
        return "Continue.dev потребує ENABLE_COMPUTER_USE=true."

    act = (action or "").strip().lower()
    if act == "open_file":
        return await _open_file(path, user_id=user_id)
    if act == "send_prompt":
        return await _send_prompt(prompt)
    if act == "get_status":
        return await _get_status()
    return (
        f"Невідома дія continue_dev: {action!r}. "
        "Доступні: open_file, send_prompt, get_status."
    )


async def _open_file(path: str, *, user_id: int) -> str:
    from ..computer import _run_cli_impl
    from ..computer_access import computer_denied_message

    denied = computer_denied_message(user_id)
    if denied:
        return denied

    target = (path or "").strip()
    if not target:
        return "path обов'язковий для open_file."

    out = await _run_cli_impl(_vscode_cli(), [target], None, trusted=True)
    if "[exit 0]" in out:
        return f"Відкрито в VS Code: {target}"
    return out


async def _get_status() -> str:
    base = _api_base()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(f"{base}/state")
            resp.raise_for_status()
            state = resp.json()
            if not isinstance(state, dict):
                return f"Continue API: неочікувана відповідь /state: {state!r}"
            return _format_status(state)
    except httpx.HTTPError as exc:
        logger.warning("continue get_status failed: %s", exc)
        return f"Continue API недоступний ({base}): {exc}"


async def _send_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        return "prompt обов'язковий для send_prompt."

    base = _api_base()
    timeout = float(settings.continue_dev_timeout or 300.0)
    poll_interval = 1.0

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            baseline = 0
            try:
                r0 = await client.get(f"{base}/state")
                r0.raise_for_status()
                state0 = r0.json()
                baseline = _history_len(state0) if isinstance(state0, dict) else 0
            except httpx.HTTPError:
                baseline = 0

            resp = await client.post(f"{base}/message", json={"message": text})
            resp.raise_for_status()
            queued = resp.json()
            if isinstance(queued, dict) and queued.get("queued") is False:
                return f"Continue не прийняв prompt: {json.dumps(queued, ensure_ascii=False)[:500]}"

            deadline = time.monotonic() + timeout
            last_state: dict[str, Any] = {}
            while time.monotonic() < deadline:
                rs = await client.get(f"{base}/state")
                rs.raise_for_status()
                raw = rs.json()
                last_state = raw if isinstance(raw, dict) else {}
                processing = bool(last_state.get("isProcessing"))
                queue = int(last_state.get("queueLength") or 0)
                pending = last_state.get("pendingPermission")
                if pending:
                    rid = pending.get("requestId", "?") if isinstance(pending, dict) else "?"
                    return (
                        f"Continue чекає підтвердження tool (requestId={rid}). "
                        "Підтверди в VS Code/CLI або виклич get_status."
                    )
                if (
                    not processing
                    and queue == 0
                    and _history_len(last_state) > baseline
                ):
                    reply = _last_assistant_text(last_state)
                    if reply:
                        return _truncate(reply)
                await asyncio.sleep(poll_interval)
    except httpx.HTTPError as exc:
        logger.warning("continue send_prompt failed: %s", exc)
        return f"Continue API недоступний ({base}): {exc}"

    hint = _format_status(last_state) if last_state else "(немає state)"
    return f"Continue timeout ({int(timeout)}s). {hint}"
