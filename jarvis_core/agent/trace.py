"""Trace-хелпери record-replay (AO-5, ARCHITECTURE_OPTIMIZATION_PLAN §2).

Перший крок event-sourced trace агент-лупу: детерміновані короткі хеші входів і
результатів інструментів. Хеш — а не сирий вміст — бо session-запис має лишатися
компактним (сирі тексти вже живуть у messages/JSONL); для replay достатньо
верифікувати збіг по хешу. Framework-нейтральний — Edge-importable (P1).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# 16 hex-символів (64 біти) — достатньо проти випадкових колізій у trace одного
# користувача; це верифікаційний хеш, не криптографічний ідентифікатор.
_HASH_LEN = 16


def short_hash(value: Any) -> str:
    """Детермінований короткий sha256-хеш будь-якого JSON-серіалізовного значення.

    Не-рядки канонізуються через json із sort_keys — однаковий dict з іншим
    порядком ключів дає той самий хеш (інакше replay-порівняння шумить).
    """
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_HASH_LEN]


def tool_trace_entry(name: str, args: Any, result: str) -> dict[str, Any]:
    """Один запис trace: виклик інструмента без сирого вмісту (hash + довжина)."""
    return {
        "tool": name,
        "args_hash": short_hash(args),
        "result_hash": short_hash(result),
        "result_len": len(result),
    }
