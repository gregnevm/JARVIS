"""Skill Scanner — скринінг SKILL.md ДО активації (ін'єкція в system-prompt).

Паттерн поля (QwenPaw Skill Scanner, `docs/COMPETITIVE_ANALYSIS.md` §3.2):
контент скіла потрапляє прямо в промпт агента (`skills.resolve_skill_block`),
тож зловмисний/імпортований скіл — це prompt-injection + інструкції на
ексфільтрацію. Сканер перевіряє тіло скіла до активації: block / warn / off.

Правила навмисно **імперативні** (дія над секретом, download-pipe-exec,
injection-фрази), а не згадки: власні скіли легітимно *пишуть про* `.env` у
своїх guardrail-настановах (auto-coder) — це не привід блокувати. Як і
exec_guard: це не межа (межа — HITL + blast_radius на діях), а дешевий
ранній фільтр із чесною причиною для audit-паспорта.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_RULES: tuple[tuple[str, str], ...] = (
    (r"(curl|wget|iwr|invoke-webrequest)[^\n]*\|\s*(ba|z)?sh\b", "download-pipe-exec"),
    (r"rm\s+-rf\s+[/~]|remove-item\b[^\n]*-recurse[^\n]*-force", "destructive-fs"),
    # \b-межі: read-дієслова матчаться як цілі токени, не як підрядки звичайних слів
    # ('type' у 'prototype', 'cat' у 'Locate'/'indicates'/'Concatenate') — інакше
    # легітимний скіл, що просто згадує .env/.ssh, блокувався б у block-режимі.
    (r"\b(cat|type|get-content|read_text)\b[^\n]{0,40}\.env\b|\bopen\([^\n]{0,40}\.env\b", "secrets-read"),
    (r"\b(cat|type|copy|scp|get-content)\b[^\n]{0,40}(id_rsa|\.ssh)", "sshkey-read"),
    (
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions"
        r"|disregard\s+(the\s+)?system\s+prompt"
        r"|ігноруй\s+(усі\s+)?попередні\s+інструкції",
        "prompt-injection",
    ),
    (r"base64\s+(-d|--decode)[^\n]*\|", "encoded-exec"),
)

_COMPILED: dict[str, re.Pattern[str]] = {}


def _pattern(expr: str) -> re.Pattern[str]:
    pat = _COMPILED.get(expr)
    if pat is None:
        pat = re.compile(expr, re.IGNORECASE)
        _COMPILED[expr] = pat
    return pat


def scan(body: str, *, extra: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Список спрацьованих правил (порожній = чисто). Політику вирішує викликач."""
    src = body or ""
    return [label for expr, label in (*_RULES, *extra) if _pattern(expr).search(src)]


def verdict(body: str, mode: str, *, extra: Iterable[tuple[str, str]] = ()) -> tuple[bool, list[str]]:
    """`(allowed, hits)` за режимом block|warn|off. Невідомий режим → block (fail-closed)."""
    normalized = (mode or "").strip().lower()
    if normalized == "off":
        return True, []
    hits = scan(body, extra=extra)
    if not hits:
        return True, []
    return (True, hits) if normalized == "warn" else (False, hits)
