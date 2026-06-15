"""Спільні helpers для Telegram bot route-handlers (bot/*)."""
from __future__ import annotations

from ..auth import is_admin
from ..telegram import TelegramClient


async def send_denial(tg: TelegramClient, chat_id: int, denied: str | None) -> bool:
    """Якщо `denied` непорожній — надіслати повідомлення-відмову й сигналізувати "оброблено".

    Узагальнює побайтово ідентичний 3-рядковий блок `if denied: await
    tg.send_message(chat_id, denied); return True`, що повторювався 11 разів
    по `bot/{remote,commands,computer,quick_actions}.py` — типовий guard перед
    Computer Use/режимними діями: `denied` обчислюється заздалегідь
    (`computer_denied_message`/`computer_mode_denied_message`/комбінації), і
    якщо команда заборонена — користувачу йде пояснення замість виконання.
    Не охоплює: компаунд-умови (`denied and len(parts) >= 2` у
    `commands.py` /mode) і callback-варіант через
    `tg.answer_callback_query` (теж `commands.py`) — інша форма відповіді,
    форсувати їх у цей хелпер означало б розгалужувати його заради двох
    нетипових місць."""
    if not denied:
        return False
    await tg.send_message(chat_id, denied)
    return True


async def require_admin_or_reply(tg: TelegramClient, chat_id: int, user_id: int | None) -> bool:
    """Якщо `user_id` не адмін — надіслати "⛔ Admin only." і сигналізувати "оброблено".

    Узагальнює побайтово ідентичний 3-рядковий блок `if not is_admin(user_id):
    await tg.send_message(chat_id, "⛔ Admin only."); return True`, повторений
    у `bot/access.py` (двічі — `acc:list` callback і `_ACC_RE` callback) та
    `bot/admin.py::handle_admin_callback` (`adm:Y`/`adm:N`).
    Не охоплює "admin only"-перевірки з КАСТОМНИМ текстом повідомлення:
    `bot/admin.py::handle_admin_command` ("⛔ Ця команда лише для адмінів
    (ADMIN_USER_IDS)."), `bot/commands.py` ×2 ("⛔ Лише для адмінів
    (ADMIN_USER_IDS)."), `bot/quick_actions.py` ("⛔ Cursor — лише для
    адмінів.") — форсувати їх у спільний текст означало б змінювати UX
    заради DRY, що того не варте (як і компаунд-варіанти `send_denial`)."""
    if is_admin(user_id):
        return False
    await tg.send_message(chat_id, "⛔ Admin only.")
    return True
