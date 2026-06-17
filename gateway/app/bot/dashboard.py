"""Рендер дашборда/довідки для Telegram у HTML parse mode.

HTML надійніший за legacy Markdown: не ламається на `_`, `.`, `(` у назвах
моделей. Метрики йдемо вирівняними колонками всередині <pre> (моноширинна
панель), динамічні значення екрануємо.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

_LABEL_W = 11  # ширина колонки-підпису (найдовший: "Code exec")


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _row(label: str, value: str) -> str:
    return f"  {label:<{_LABEL_W}}{value}"


def _panel(rows: list[str]) -> str:
    return "<pre>" + "\n".join(rows) + "</pre>"


def format_dashboard(data: dict[str, Any], twin: dict[str, Any]) -> str:
    rows: list[str] = []

    if data.get("error"):
        rows.append("CORE")
        rows.append(_row("Tools", f"🔴 {esc(data['error'])}"))
    elif data:
        up = data.get("ollama_up")
        code_on = bool(data.get("code_exec"))
        rows.append("CORE")
        rows.append(_row("Режим", esc(data.get("agent_mode", "?"))))
        rows.append(_row("Ollama", f"{'🟢' if up else '🔴'} {esc(data.get('ollama_host', ''))}"))
        rows.append(_row("Chat", esc(data.get("chat_model", "—"))))
        rows.append(_row("Agent", esc(data.get("agent_model", "—"))))
        rows.append(_row("Code exec", f"{'🟢 on' if code_on else '⚪ off'}"))

    if twin:
        edges = twin.get("edges") or {}
        active = twin.get("active_lora")
        if rows:
            rows.append("")
        rows.append("TWIN")
        rows.append(_row("Edge logs", f"{sum(edges.values())}  ({len(edges)} edge)"))
        if active:
            rows.append(_row("LoRA", f"v{esc(active.get('version'))} · eval {esc(active.get('eval_score'))}"))
        else:
            rows.append(_row("LoRA", "—"))

    if not rows:
        rows.append("немає даних")

    ts = datetime.now().strftime("%H:%M")
    return f"🧩 <b>JARVIS</b> · панель\n{_panel(rows)}<i>оновлено {ts}</i>"


def format_help() -> str:
    return (
        "🎛 <b>JARVIS — команди</b>\n\n"
        "<b>/start</b> · головне меню + швидкі кнопки\n"
        "<b>/dashboard</b> · панель + inline-кнопки\n"
        "<b>/app</b> · Mini App (HTTPS URL у PUBLIC_APP_URL)\n"
        "<b>/start app</b> · deep link до Mini App\n"
        "<b>/status</b> · стан сервісів\n"
        "<b>/brief</b> · короткий бриф (система + нагадування)\n"
        "<b>/reminders</b> · активні нагадування · <code>/reminders ics</code>\n"
        "<b>/project</b> · проєкти (ізольований RAG + інструкції) · <code>/project new Назва</code>\n"
        "<b>/mode</b> · поточний режим\n"
        "<b>/mode</b> <code>chat|agent|hybrid|computer</code> · змінити роутинг\n"
        "<b>/plan</b> <code>&lt;задача&gt;</code> · план з підтвердженням\n"
        "<b>/cursor</b> <code>&lt;задача&gt;</code> · Cursor IDE (admin) · <code>/cursor ask</code>\n"
        "<b>/apk</b> · MVP Android-клієнт (.apk) у Telegram\n"
        "<b>/sync</b> · Twin ingest + LoRA\n"
        "<b>/keyboard</b> <code>on|off</code> · reply-клавіатура\n"
        "<b>/admin</b> · Admin Mini App у Telegram (HTTPS) + inline-дії з підтвердженням\n"
        "<b>/confirm</b> <code>КОД</code> · підтвердити admin-дію\n"
        "<b>/pending</b> · черга запитів на доступ (адмін)\n"
        "<b>/allow</b> <code>ID</code> · погодити друга (адмін)\n"
        "<b>/deny</b> · відхилити · <b>/revoke</b> · забрати доступ\n"
        "<b>/help</b> · ця довідка\n\n"
        "<b>Швидкі кнопки</b> під полем вводу: Статус, Бриф, Нагадування, Computer.\n"
        "<b>Inline</b>: @bot у будь-якому чаті — запит до JARVIS.\n"
        "<b>Реакції</b> emoji на відповідь бота — коротка репліка.\n\n"
        "📸 Скріншот / PC: <code>/mode computer</code> або hybrid + «скріншот», «winget», «powershell».\n"
        "🧠 Cursor coding: <code>/cursor …</code> або в computer mode — «постав cursor задачу …».\n"
        "<b>Remote:</b> <code>/file C:\\path</code> · <code>/macro list|run</code> · "
        "<code>/see</code> · <code>/clipboard</code> · <code>/tasks</code>\n"
        "📥 Drop zone: надішли файл з підписом <code>на диск: C:\\Users\\…\\file</code>\n"
        "💬 <i>Надсилай будь-що</i> — текст, голос/аудіо/відео (розпізнаю), фото, "
        "документи (txt/pdf/docx/...), стікери, локацію, контакти — усе йде до агента. "
        "Відповідь теж може містити медіа (фото/файли/локацію)."
    )
