"""Remote commands: /file, /macro, /tasks, /see, drop zone."""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

from ..auth import computer_denied_message
from ..config import settings
from ..outbound import deliver
from ..telegram import TelegramClient
from ..tools_client import ToolsClient

logger = logging.getLogger("jarvis.gateway.remote")

_DROP_RE = re.compile(r"на\s+диск\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)
_COMPUTER_HINT_RE = re.compile(
    r"(скріншот|powershell|winget|docker|файл\s+на|на\s+хост|комп.?ютер)",
    re.IGNORECASE,
)


def looks_like_computer_request(text: str) -> bool:
    return bool(_COMPUTER_HINT_RE.search(text or ""))


def is_remote_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return t.startswith(("/file", "/macro", "/tasks", "/see", "/clipboard"))


async def handle_remote_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    *,
    redis: Any | None = None,
) -> bool:
    denied = computer_denied_message(user_id)
    t = (text or "").strip()
    low = t.lower()
    if low.startswith("/file"):
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            await tg.send_message(chat_id, "Використання: <code>/file C:\\path\\to\\file</code>", parse_mode="HTML")
            return True
        path = parts[1].strip()
        data = await tools.pull_file(user_id, path)
        if data.get("error"):
            await tg.send_message(chat_id, str(data["error"]))
            return True
        raw = base64.b64decode(str(data.get("data_b64", "")))
        fname = str(data.get("filename") or Path(path).name)
        await tg.send_document(chat_id, raw, filename=fname)
        return True

    if low.startswith("/macro"):
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        parts = t.split(maxsplit=2)
        if len(parts) < 2 or parts[1].lower() == "list":
            macros = await tools.list_macros()
            lines = ["<b>Макроси:</b>"]
            for m in macros.get("macros") or []:
                lines.append(f"• <code>{m.get('name')}</code> — {m.get('description', '')}")
            lines.append("\n/macro run &lt;name&gt;")
            await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
            return True
        if parts[1].lower() == "run" and len(parts) >= 3:
            result = await tools.run_macro(user_id, parts[2])
            await deliver(tg, chat_id, result, redis=redis, user_id=user_id)
            return True
        await tg.send_message(chat_id, "/macro list | /macro run &lt;name&gt;", parse_mode="HTML")
        return True

    if low.startswith("/tasks"):
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        if "cancel" in low:
            await tools.cancel_tasks(user_id)
            await tg.send_message(chat_id, "Задачі скасовано.")
            return True
        body = await tools.list_tasks(user_id)
        await tg.send_message(chat_id, body)
        return True

    if low.startswith("/see"):
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        q = t.split(maxsplit=1)[1] if " " in t else ""
        await tg.send_chat_action(chat_id, "upload_photo")
        reply = await tools.see_screen(user_id, q)
        await deliver(tg, chat_id, reply, redis=redis, user_id=user_id)
        return True

    if low.startswith("/clipboard"):
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        reply = await tools.clipboard_read(user_id)
        await tg.send_message(chat_id, reply[:4000])
        return True

    return False


async def maybe_drop_to_host(
    message: dict[str, Any],
    saved_path: str,
    caption: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
) -> bool:
    """Caption «на диск: C:\\...» або HOSTAGENT_DROP_DIR."""
    denied = computer_denied_message(user_id)
    if denied:
        return False
    dest = ""
    m = _DROP_RE.search(caption or "")
    if m:
        dest = m.group(1).strip()
    elif settings.hostagent_drop_dir.strip():
        dest = str(Path(settings.hostagent_drop_dir) / Path(saved_path).name)
    if not dest:
        return False
    try:
        data = Path(saved_path).read_bytes()
    except OSError as exc:
        await tg.send_message(chat_id, f"Не вдалося прочитати файл: {exc}")
        return True
    b64 = base64.b64encode(data).decode("ascii")
    result = await tools.push_file(user_id, dest, b64)
    await tg.send_message(chat_id, result.get("text") or result.get("error") or "Готово.")
    return True
