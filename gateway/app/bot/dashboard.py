from __future__ import annotations

from typing import Any


def format_dashboard(data: dict[str, Any], twin: dict[str, Any]) -> str:
    lines = ["📊 *JARVIS Dashboard*", ""]
    if data.get("error"):
        lines.append(f"⚠️ Tools: `{data['error']}`")
    else:
        mode = data.get("agent_mode", "?")
        lines.append(f"• Режим: `{mode}`")
        lines.append(f"• Ollama: {'🟢' if data.get('ollama_up') else '🔴'} `{data.get('ollama_host', '')}`")
        lines.append(f"• Chat model: `{data.get('chat_model', '')}`")
        lines.append(f"• Agent model: `{data.get('agent_model', '')}`")
        lines.append(f"• Code exec: `{'on' if data.get('code_exec') else 'off'}`")
    if twin:
        edges = twin.get("edges") or {}
        active = twin.get("active_lora")
        lines.append("")
        lines.append("*Twin Sync*")
        lines.append(f"• Edge logs: `{sum(edges.values())}` записів ({len(edges)} edge)")
        if active:
            lines.append(f"• Active LoRA: `{active.get('version')}` (eval {active.get('eval_score')})")
        else:
            lines.append("• Active LoRA: немає")
    lines.append("")
    lines.append("_Команди: /help /status /mode /dashboard_")
    return "\n".join(lines)


def format_help() -> str:
    return (
        "🎛 *JARVIS — команди*\n\n"
        "/start — головне меню\n"
        "/dashboard — панель + кнопки\n"
        "/status — стан сервісів\n"
        "/mode — поточний режим\n"
        "/mode chat|agent|hybrid — змінити роутинг\n"
        "/sync — Twin ingest + LoRA\n"
        "/admin — панель адміна (з підтвердженням)\n"
        "/confirm КОД — підтвердити admin-дію\n"
        "/help — ця довідка\n\n"
        "Текст і будь-яке аудіо (голосові, MP3, відео-нотатки, відео) — запит до агента."
    )
