from __future__ import annotations

from typing import Any

from ..telegram_webapp_auth import admin_app_url

# Тексти кнопок reply-клавіатури (мапінг у quick_actions.py).
BTN_STATUS = "📊 Статус"
BTN_BRIEF = "📋 Бриф"
BTN_REMINDERS = "⏰ Нагадування"
BTN_COMPUTER = "💻 Computer"
BTN_SCREEN = "📸 Скрін"
BTN_MENU = "🎛 Меню"
BTN_CLIPBOARD = "📋 Буфер"
BTN_HIDE = "⌨️ Сховати"


def reply_keyboard(app_url: str | None = None, *, show_computer: bool = True) -> dict[str, Any]:
    """Reply Keyboard — постійні кнопки під полем вводу."""
    rows: list[list[dict[str, Any]]] = [
        [{"text": BTN_STATUS}, {"text": BTN_BRIEF}],
    ]
    if show_computer:
        rows.append([{"text": BTN_REMINDERS}, {"text": BTN_SCREEN}])
        rows.append([{"text": BTN_CLIPBOARD}, {"text": BTN_COMPUTER}])
        rows.append([{"text": BTN_MENU}])
    else:
        rows.append([{"text": BTN_REMINDERS}, {"text": BTN_MENU}])
    rows.append([{"text": BTN_HIDE}])
    if app_url and app_url.startswith("https://"):
        rows.insert(0, [{"text": "📊 Dashboard", "web_app": {"url": app_url}}])
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Запит до JARVIS…",
    }


def remove_reply_keyboard() -> dict[str, Any]:
    return {"remove_keyboard": True}


def main_menu_keyboard(
    app_url: str | None = None, *, show_computer: bool = True
) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    if app_url and app_url.startswith("https://"):
        rows.append([{"text": "📊 Відкрити дашборд", "web_app": {"url": app_url}}])
    rows.extend(
        [
            [
                {"text": "📊 Статус", "callback_data": "dash:status"},
                {"text": "📋 Бриф", "callback_data": "dash:brief"},
            ],
            [
                {"text": "🧠 Режим", "callback_data": "dash:mode"},
                {"text": "⏰ Нагадування", "callback_data": "dash:reminders"},
            ],
            [
                {"text": "💬 Чат", "callback_data": "mode:chat"},
                {"text": "🤖 Агент", "callback_data": "mode:agent"},
            ],
            [
                {"text": "⚖️ Гібрид", "callback_data": "mode:hybrid"},
                *(
                    [{"text": "💻 Computer", "callback_data": "mode:computer"}]
                    if show_computer
                    else []
                ),
            ],
            [
                {"text": "🔄 Sync / LoRA", "callback_data": "dash:sync"},
                {"text": "❓ Довідка", "callback_data": "dash:help"},
            ],
        ]
    )
    return {"inline_keyboard": rows}


def admin_menu_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    url = admin_app_url()
    if url.startswith("https://"):
        rows.append([{"text": "🛠 Admin Control Panel", "web_app": {"url": url}}])
    rows.extend(
        [
            [
                {"text": "Mode → Chat", "callback_data": "adm:Y:m:chat"},
                {"text": "Mode → Agent", "callback_data": "adm:Y:m:agent"},
            ],
            [
                {"text": "Mode → Hybrid", "callback_data": "adm:Y:m:hybrid"},
                {"text": "Mode → Computer", "callback_data": "adm:Y:m:computer"},
            ],
            [{"text": "↩️ Reset mode (.env)", "callback_data": "adm:Y:r"}],
            [{"text": "📋 Запити доступу", "callback_data": "acc:list"}],
            [{"text": "🔓 Мій rate-limit", "callback_data": "adm:Y:rl:self"}],
            [{"text": "« Звичайне меню", "callback_data": "dash:menu"}],
        ]
    )
    return {"inline_keyboard": rows}


def access_decision_keyboard(user_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Дозволити", "callback_data": f"acc:y:{user_id}"},
                {"text": "❌ Відхилити", "callback_data": f"acc:n:{user_id}"},
            ]
        ]
    }


def admin_confirm_keyboard(action: str, code: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Підтвердити", "callback_data": f"adm:Y:{code}"},
                {"text": "❌ Скасувати", "callback_data": "adm:N:0"},
            ]
        ]
    }


def computer_confirm_keyboard(code: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Підтвердити", "callback_data": f"cmp:Y:{code}"},
                {"text": "✅ + Trust 30х", "callback_data": f"cmp:YT:{code}"},
            ],
            [{"text": "❌ Скасувати", "callback_data": "cmp:N:0"}],
        ]
    }


def admin_ps_confirm_keyboard(code: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔴 Підтвердити Admin PS",
                    "callback_data": f"cmpA:Y:{code}",
                },
            ],
            [{"text": "❌ Скасувати", "callback_data": "cmp:N:0"}],
        ]
    }


def mode_keyboard(*, show_computer: bool = True) -> dict[str, Any]:
    mode_row: list[dict[str, str]] = [
        {"text": "⚖️ Гібрид", "callback_data": "mode:hybrid"},
    ]
    if show_computer:
        mode_row.append({"text": "💻 Computer", "callback_data": "mode:computer"})
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Чат", "callback_data": "mode:chat"},
                {"text": "🤖 Агент", "callback_data": "mode:agent"},
            ],
            mode_row,
            [{"text": "« Меню", "callback_data": "dash:menu"}],
        ]
    }


def reminders_hint_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔄 Оновити", "callback_data": "dash:reminders"}],
            [{"text": "« Меню", "callback_data": "dash:menu"}],
        ]
    }
