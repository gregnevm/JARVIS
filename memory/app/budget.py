"""Token-budget утиліти для context-assembly (CA-2.5).

Евристика ~4 символи/токен (Llama/Ollama, емпірично) — без залежності від
зовнішнього токенайзера. Достатньо, щоб бюджетувати інжект файлів проєкту в
системний промпт під вікно контексту передбачувано (на відміну від char-ліміту,
де «12k символів» — це різна к-сть токенів для коду vs прози).

Релевантність файлів забезпечує scoped-RAG (CA-2.4); цей модуль лише ОБМЕЖУЄ
сукупний обсяг того, що інжектиться повним вмістом (P1.7).
"""
from __future__ import annotations

import math

_CHARS_PER_TOKEN = 4
_TRUNC_MARK = "…[truncated]"


def estimate_tokens(text: str) -> int:
    """Груба оцінка к-сті токенів (ceil(len/4)); 0 для порожнього рядка."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def fit_token_budget(
    items: list[dict[str, str]],
    *,
    max_total_tokens: int,
    max_per_item_tokens: int,
    key: str = "content",
) -> list[dict[str, str]]:
    """Включає items по черзі під сукупний токен-бюджет; кожен обрізає до
    per-item ліміту (і до залишку бюджету). Стоп, коли бюджет вичерпано.

    Повертає НОВІ dict-и (не мутує вхід); поле `key` може бути обрізане з
    маркером. Решта полів (напр. `name`) копіюються як є."""
    out: list[dict[str, str]] = []
    budget = max(0, int(max_total_tokens))
    per_cap_tokens = max(0, int(max_per_item_tokens))
    for it in items:
        if budget <= 0:
            break
        raw = str(it.get(key, ""))
        cap_tokens = min(per_cap_tokens, budget)
        cap_chars = cap_tokens * _CHARS_PER_TOKEN
        content = raw[:cap_chars] + _TRUNC_MARK if len(raw) > cap_chars else raw
        new = dict(it)
        new[key] = content
        out.append(new)
        budget -= estimate_tokens(content)
    return out
