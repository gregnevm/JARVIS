"""Redactor — серверна (друга) редакція перед store (Strategy, DESIGN §1.2.1).

Вирізає очевидні секрети/PII регулярками ДО персисту: картки, IBAN, API-ключі,
OTP-коди (за ключовим словом). Чистий стандартний `re`, без залежностей —
імпортовний на Edge. Перша редакція — на пристрої (device pre-redact); це бекстоп.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Pattern

from .models import Passport, should_store_raw


@dataclass
class Rule:
    name: str
    pattern: Pattern[str]
    # repl: рядок-заміна, АБО callable(Match)->str (коли треба вирізати лише групу).
    repl: "str | Callable[[re.Match[str]], str]"


def _otp_repl(m: re.Match[str]) -> str:
    """Зберігає ключове слово, маскує лише цифри коду: 'код 1234' → 'код [REDACTED:otp]'."""
    return m.group(0).replace(m.group("code"), "[REDACTED:otp]")


_DEFAULT_RULES: list[Rule] = [
    # Платіжна картка: 13–19 цифр, опц. розділювачі (групами по 4).
    Rule("card", re.compile(r"\b\d{4}(?:[ -]?\d{4}){2,4}\b"), "[REDACTED:card]"),
    # IBAN: 2 літери + 2 цифри + 10–30 alnum.
    Rule("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "[REDACTED:iban]"),
    # API-ключі/токени: sk-/pk-/ghp_/xoxb-… + ≥16 alnum.
    Rule(
        "secret",
        re.compile(r"\b(?:sk|pk|ghp|xox[bp])[-_][A-Za-z0-9]{16,}\b"),
        "[REDACTED:secret]",
    ),
    # OTP/пароль: ключове слово, далі 4–8 цифр (маскуємо лише цифри).
    Rule(
        "otp",
        re.compile(
            r"(?i)(?:otp|code|код|пароль|password|verification|підтвердж\w*)\D{0,20}?"
            r"(?P<code>\d{4,8})\b"
        ),
        _otp_repl,
    ),
]


class Redactor:
    """Прогоняє текст крізь правила-Strategy. Порядок правил визначає пріоритет."""

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = rules if rules is not None else _DEFAULT_RULES

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        for rule in self._rules:
            out = rule.pattern.sub(rule.repl, out)
        return out

    def redact_passport(self, p: Passport) -> Passport:
        """Редагує summary; payload — редагує або повністю прибирає за sensitivity."""
        from dataclasses import replace

        clean_summary = self.redact(p.summary)
        if should_store_raw(p.sensitivity):
            payload = self._redact_payload(p.payload)
        else:
            payload = {}  # health/finance — сире не зберігаємо взагалі
        return replace(p, summary=clean_summary, payload=payload)

    def _redact_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in (payload or {}).items():
            out[k] = self.redact(v) if isinstance(v, str) else v
        return out


_default = Redactor()


def default_redactor() -> Redactor:
    return _default
