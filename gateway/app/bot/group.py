"""Telegram group presence (Стовп D / TEAM_ECOSYSTEM TC-2).

Окремий шлях для chat.type group/supergroup (приватний flow незмінний — S2).
Рівні згоди (`tg_groups.ingest`): off (мовчати/нічого не збирати, дефолт),
addressed (реагувати/збирати лише на @mention або reply на бота), ambient
(пасивно збирати всі повідомлення в паспорти — лише з явної згоди адміна).

Логіка рішення — чиста функція `decide_group_action` (легко тестується); I/O
(ідентифікація членів, збір у memory, відповідь) — оркестратор `handle_group_message`.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.gateway.group")

# Рівні згоди на обробку групи (дзеркалить tg_groups.ingest).
INGEST_LEVELS = frozenset({"off", "addressed", "ambient"})

# Можливі рішення для групового повідомлення.
ACTION_IGNORE = "ignore"     # нічого не робимо
ACTION_COLLECT = "collect"   # тихо зібрати в паспорт (ambient)
ACTION_RESPOND = "respond"   # відповісти як делегат (+ зібрати)


def is_addressed(message: dict[str, Any], bot_username: str, bot_id: int | None = None) -> bool:
    """Чи звернене повідомлення до бота: @mention у тексті або reply на бота."""
    reply = message.get("reply_to_message") or {}
    if bot_id is not None and (reply.get("from") or {}).get("id") == bot_id:
        return True
    text = str(message.get("text") or message.get("caption") or "")
    handle = bot_username.lstrip("@").lower()
    if not handle:
        return False
    # перевіряємо entities mention або простий підрядок @handle
    if f"@{handle}" in text.lower():
        return True
    return False


def decide_group_action(*, ingest: str, addressed: bool) -> str:
    """Чиста політика: рівень згоди + чи звернене → що робити.

    - off → завжди ignore (бот мовчить, нічого не збирає);
    - addressed → respond лише якщо звернене, інакше ignore;
    - ambient → respond якщо звернене, інакше collect (пасивний збір).
    """
    level = ingest if ingest in INGEST_LEVELS else "off"
    if level == "off":
        return ACTION_IGNORE
    if addressed:
        return ACTION_RESPOND
    return ACTION_COLLECT if level == "ambient" else ACTION_IGNORE


def member_identity(message: dict[str, Any]) -> dict[str, Any] | None:
    """Витягує (telegram_id, name) автора для upsert у tg_group_members."""
    frm = message.get("from") or {}
    tid = frm.get("id")
    if tid is None:
        return None
    name = (frm.get("username") or frm.get("first_name") or "").strip()
    return {"telegram_id": int(tid), "name": name}


async def handle_group_message(
    message: dict[str, Any],
    chat: dict[str, Any],
    *,
    tg: Any,
    group_store: Any,
    bot_username: str = "",
    bot_id: int | None = None,
) -> str:
    """Оркеструє груповий шлях. Повертає вжите рішення (для логів/тестів).

    `group_store` — клієнт із async-методами `get_ingest(chat_id)`,
    `upsert_member(chat_id, telegram_id, name)`, `collect(chat_id, message)`,
    `respond(chat_id, message)`. Best-effort: будь-яка помилка → ignore (не валимо бота).
    """
    chat_id = chat.get("id")
    if chat_id is None:
        return ACTION_IGNORE
    try:
        ingest = await group_store.get_ingest(int(chat_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("group ingest lookup failed for %s: %s", chat_id, exc)
        return ACTION_IGNORE

    ident = member_identity(message)
    if ident is not None and ingest != "off":
        try:
            await group_store.upsert_member(int(chat_id), ident["telegram_id"], ident["name"])
        except Exception as exc:  # noqa: BLE001
            logger.debug("member upsert failed: %s", exc)

    action = decide_group_action(ingest=ingest, addressed=is_addressed(message, bot_username, bot_id))
    if action == ACTION_COLLECT:
        await group_store.collect(int(chat_id), message)
    elif action == ACTION_RESPOND:
        await group_store.respond(int(chat_id), message)
    return action
