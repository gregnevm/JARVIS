"""Перевірка PS_WHITELIST для Computer Use."""
from __future__ import annotations

import re


def parse_whitelist(raw: str) -> set[str]:
    return {x.strip().lower() for x in (raw or "").split(",") if x.strip()}


def extract_ps_cmdlets(script: str) -> list[str]:
    """Перший токен кожної інструкції PowerShell (розділювач `;` або новий рядок)."""
    cmdlets: list[str] = []
    for part in re.split(r"[;\r\n]+", script or ""):
        part = part.strip()
        if not part or part.startswith("#"):
            continue
        first = part.split(None, 1)[0].lower().rstrip(";")
        if first:
            cmdlets.append(first)
    return cmdlets


_FORBIDDEN = re.compile(
    r"\|(?![^\n]*\|)|&&|\|\||`|\$\(|Invoke-Expression|Start-Process",
    re.IGNORECASE,
)


def check_ps_whitelist(script: str, *, trusted: bool = False) -> str | None:
    """trusted=True — після ✅ у Telegram (користувач уже підтвердив дію)."""
    if trusted:
        if _FORBIDDEN.search(script or ""):
            return "PowerShell: заборонені оператори (| && || ` $( ) або небезпечні cmdlet)."
        return None
    from .computer_learned import effective_ps_allowed

    allowed = effective_ps_allowed()
    if not allowed:
        return "PowerShell вимкнено: PS_WHITELIST порожній і ще немає навчених команд."
    if _FORBIDDEN.search(script or ""):
        return "PowerShell: заборонені оператори (| && || ` $( ) або небезпечні cmdlet)."
    cmdlets = extract_ps_cmdlets(script)
    if not cmdlets:
        return "Порожній PowerShell-скрипт."
    for cmd in cmdlets:
        if cmd not in allowed:
            return f"PowerShell-команда '{cmd}' не в PS_WHITELIST."
    return None
