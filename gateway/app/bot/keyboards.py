from __future__ import annotations

from typing import Any


def main_menu_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Статус", "callback_data": "dash:status"},
                {"text": "🧠 Режим", "callback_data": "dash:mode"},
            ],
            [
                {"text": "💬 Chat", "callback_data": "mode:chat"},
                {"text": "🤖 Agent", "callback_data": "mode:agent"},
                {"text": "⚖️ Hybrid", "callback_data": "mode:hybrid"},
            ],
            [
                {"text": "🔄 Sync / LoRA", "callback_data": "dash:sync"},
                {"text": "❓ Довідка", "callback_data": "dash:help"},
            ],
        ]
    }


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
