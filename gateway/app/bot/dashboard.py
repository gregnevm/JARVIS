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
        "<b>/start</b> · головне меню\n"
        "<b>/dashboard</b> · панель + кнопки\n"
        "<b>/status</b> · стан сервісів\n"
        "<b>/mode</b> · поточний режим\n"
        "<b>/mode</b> <code>chat|agent|hybrid</code> · змінити роутинг\n"
        "<b>/sync</b> · Twin ingest + LoRA\n"
        "<b>/admin</b> · панель адміна (з підтвердженням)\n"
        "<b>/confirm</b> <code>КОД</code> · підтвердити admin-дію\n"
        "<b>/help</b> · ця довідка\n\n"
        "💬 <i>Текст і будь-яке аудіо</i> — голосові, MP3, відео-нотатки, відео — "
        "це запит до агента."
    )
