from __future__ import annotations

from typing import Any


def main_menu_keyboard(app_url: str | None = None) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    # Telegram приймає web_app-кнопки лише з https-URL.
    if app_url and app_url.startswith("https://"):
        rows.append([{"text": "📊 Відкрити дашборд", "web_app": {"url": app_url}}])
    rows.extend(
        [
            [
                {"text": "📊 Статус", "callback_data": "dash:status"},
                {"text": "🧠 Режим", "callback_data": "dash:mode"},
            ],
            [
                {"text": "💬 Chat", "callback_data": "mode:chat"},
                {"text": "🤖 Agent", "callback_data": "mode:agent"},
                {"text": "⚖️ Hybrid", "callback_data": "mode:hybrid"},
            ],
            [{"text": "💻 Computer", "callback_data": "mode:computer"}],
            [
                {"text": "🔄 Sync / LoRA", "callback_data": "dash:sync"},
                {"text": "❓ Довідка", "callback_data": "dash:help"},
            ],
        ]
    )
    return {"inline_keyboard": rows}


def admin_menu_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Mode → Chat", "callback_data": "adm:Y:m:chat"},
                {"text": "Mode → Agent", "callback_data": "adm:Y:m:agent"},
            ],
            [{"text": "Mode → Hybrid", "callback_data": "adm:Y:m:hybrid"}],
            [{"text": "↩️ Reset mode (.env)", "callback_data": "adm:Y:r"}],
            [{"text": "🔓 Мій rate-limit", "callback_data": "adm:Y:rl:self"}],
            [{"text": "« Звичайне меню", "callback_data": "dash:menu"}],
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
                {"text": "❌ Скасувати", "callback_data": "cmp:N:0"},
            ]
        ]
    }


def mode_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Chat", "callback_data": "mode:chat"},
                {"text": "🤖 Agent", "callback_data": "mode:agent"},
            ],
            [{"text": "⚖️ Hybrid", "callback_data": "mode:hybrid"}],
            [{"text": "« Меню", "callback_data": "dash:menu"}],
        ]
    }
