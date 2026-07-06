"""Pre-exec guard — статичний скринінг коду перед `code_exec` (defense-in-depth).

Другий шар обвʼязки виконання коду (перший — kernel-sandbox, див.
`tools/app/toolkit/sandbox.py`): дешева перевірка джерела на очевидні спроби
ексфільтрації секретів / втечі з пісочниці ДО запуску процесу. Паттерн «Tool
Guard» з поля (QwenPaw): кожен виклик інструмента проходить правила до виконання
(`docs/COMPETITIVE_ANALYSIS.md` §3.5).

**Це НЕ security-межа** — статичний скринінг Python обходиться тривіально
(getattr, кодування, eval). Межа — bwrap/ізоляція процесу. Guard дає: (а) чесну
причину відмови для audit-паспорта замість мовчазного фейлу в пісочниці, (б)
захист fallback-режиму без пісочниці, (в) конфігуровані домен-правила з профілю.

**FAIL-CLOSED по збігу:** будь-який збіг deny-правила → відмова, reason придатний
для human-gate-повідомлення (як у `blast_radius.decide`). Правила — регекси,
компілюються ліниво; профільні правила додаються до вбудованих, не замінюють їх.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

# Вбудований мінімум: ексфільтрація env/секретів, спавн процесів, сирі сокети,
# обхід ізоляції інтерпретатора. Свідомо короткий — false positive у code_exec
# дратує, а межу тримає sandbox; домен-специфіку додає профіль через `extra`.
_BUILTIN_RULES: tuple[tuple[str, str], ...] = (
    (r"\bos\.environ\b|\bos\.getenv\b", "env-exfiltration"),
    (r"\bsubprocess\b|\bos\.system\b|\bos\.exec[a-z]*\b|\bos\.spawn[a-z]*\b|\bpty\b", "process-spawn"),
    (r"\bsocket\b|\bctypes\b", "raw-socket/ffi"),
    (r"\.env\b|/proc/self/environ", "secrets-file"),
    (r"\bimportlib\b.*\breload\b|\b__loader__\b|\b__import__\s*\(", "import-bypass"),
)

_COMPILED: dict[str, re.Pattern[str]] = {}


def _pattern(expr: str) -> re.Pattern[str]:
    pat = _COMPILED.get(expr)
    if pat is None:
        pat = re.compile(expr, re.IGNORECASE)
        _COMPILED[expr] = pat
    return pat


def parse_extra_rules(raw: str) -> tuple[tuple[str, str], ...]:
    """CSV `regex` або `regex=label` з settings → правила. Некомпільовне — ігнор.

    Некомпільовний регекс тут свідомо НЕ fail-closed: він означає помилку
    конфігурації оператора, а не небезпечний код; блокувати весь code_exec через
    друкарську помилку в `.env` — гірше, ніж пропустити одне кастомне правило
    (вбудовані лишаються чинними завжди).
    """
    rules: list[tuple[str, str]] = []
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        expr, _, label = item.partition("=")
        expr = expr.strip()
        try:
            re.compile(expr)
        except re.error:
            continue
        rules.append((expr, label.strip() or "profile-rule"))
    return tuple(rules)


def screen(code: str, *, extra: Iterable[tuple[str, str]] = ()) -> tuple[bool, str]:
    """`(allowed, reason)` — reason називає правило (для audit-паспорта).

    Порожній код дозволяємо: не наша вісь (валідує сам code_exec).
    """
    src = code or ""
    for expr, label in (*_BUILTIN_RULES, *extra):
        if _pattern(expr).search(src):
            return False, f"deny:{label}"
    return True, "clean"
