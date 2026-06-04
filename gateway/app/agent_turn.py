"""Єдиний шлях виконання агента та resume після Computer Use confirm."""
from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from .config import settings
from .outbound import deliver
from .streaming import stream_reply
from .telegram import TelegramClient
from .tools_client import ToolsClient


async def run_agent_turn(
    tg: TelegramClient,
    tools: ToolsClient,
    chat_id: int,
    payload: dict[str, Any],
    react_message_id: int | None = None,
    redis: aioredis.Redis | None = None,
    user_id: int | None = None,
    message_thread_id: int | None = None,
) -> str:
    """Виконує запит до агента й доставляє відповідь (текст + медіа/кнопки/реакції/канвас)."""
    thread_id = message_thread_id
    if thread_id is None and payload.get("message_thread_id") is not None:
        thread_id = int(payload["message_thread_id"])
    uid = user_id if user_id is not None else int(payload.get("user_id") or chat_id)

    if settings.enable_streaming:
        reply = await stream_reply(
            tg,
            tools,
            chat_id,
            payload,
            react_message_id,
            redis=redis,
            user_id=uid,
            message_thread_id=thread_id,
        )
        if not reply:
            reply = await tools.process(payload)
            reply = await deliver(
                tg,
                chat_id,
                reply,
                react_message_id,
                redis=redis,
                user_id=uid,
                message_thread_id=thread_id,
            )
        return reply
    reply = await tools.process(payload)
    return await deliver(
        tg,
        chat_id,
        reply,
        react_message_id,
        redis=redis,
        user_id=uid,
        message_thread_id=thread_id,
    )


async def resume_after_computer(
    tg: TelegramClient,
    tools: ToolsClient,
    chat_id: int,
    user_id: int,
    result: str,
    redis: aioredis.Redis | None = None,
    *,
    origin_text: str = "",
    message_thread_id: int | None = None,
) -> str:
    """Другий хід агента після підтвердженої Computer Use дії."""
    from .auth import computer_denied_message

    denied = computer_denied_message(user_id)
    if denied:
        await tg.send_message(chat_id, denied, message_thread_id=message_thread_id)
        return denied
    origin = (origin_text or "").strip()
    parts = []
    if origin:
        parts.append(f"Оригінальний запит користувача:\n{origin[:3000]}")
    parts.append(f"Результат підтвердженої Computer Use дії на хості:\n{result[:6000]}")
    parts.append(
        "Коротко підсумуй для користувача українською. "
        "Якщо початкове завдання ще не виконано — продовж наступним кроком."
    )
    await tg.send_chat_action(chat_id, "typing")
    return await run_agent_turn(
        tg,
        tools,
        chat_id,
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "text": "\n\n".join(parts),
            "type": "computer_resume",
            "mode": "computer",
            "message_thread_id": message_thread_id,
        },
        redis=redis,
        user_id=user_id,
        message_thread_id=message_thread_id,
    )
