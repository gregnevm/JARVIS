"""Approval-драбина Computer Use — один іменований рівень замість трьох прапорів.

Паттерн поля 2026 (`docs/COMPETITIVE_ANALYSIS.md` §3.4: QwenPaw
STRICT/SMART/AUTO/OFF, Open Interpreter untrusted/on-request/never): оператор
обирає ОДИН рівень, а не жонглює комбінаціями. Семантика на наших механізмах:

  strict — кожна мутуюча дія → ✅; auto-trust learned вимкнено (навчання
           whitelist лишається — набирає дані, але не діє).
  smart  — ✅ + learned auto-trust (дефолт-поведінка прапорів).
  auto   — мутуючі computer-дії без ✅; майстер-bypass (headless/plans) НЕ
           вмикається; admin-gate (computer_allow_admin) — завжди свій.
  off    — майстер-bypass усіх підтверджень (= BYPASS_CONFIRMATIONS=true).

`COMPUTER_APPROVAL_POLICY=""` (дефолт) — політика не задана, читаються
гранулярні прапори (повний back-compat). Задана політика — SSOT і перекриває
прапори (P7); резолвери нижче — єдина точка читання для confirm-шляхів.
Невідоме значення → fail-closed у strict (безпечніше за мовчазний дефолт).
"""
from __future__ import annotations

from .config import settings

POLICIES = ("strict", "smart", "auto", "off")

# policy → (require_confirm, auto_trust_learned, bypass_confirmations)
_MATRIX: dict[str, tuple[bool, bool, bool]] = {
    "strict": (True, False, False),
    "smart": (True, True, False),
    "auto": (False, True, False),
    "off": (False, True, True),
}


def policy() -> str:
    """Нормалізована політика; "" = не задана; невідома → strict (fail-closed)."""
    raw = (settings.computer_approval_policy or "").strip().lower()
    if not raw:
        return ""
    return raw if raw in _MATRIX else "strict"


def _resolved() -> tuple[bool, bool, bool] | None:
    name = policy()
    return _MATRIX[name] if name else None


def require_confirm() -> bool:
    row = _resolved()
    return row[0] if row else bool(settings.computer_require_confirm)


def auto_trust_learned() -> bool:
    row = _resolved()
    return row[1] if row else bool(settings.computer_auto_trust_learned)


def bypass_confirmations() -> bool:
    row = _resolved()
    return row[2] if row else bool(settings.bypass_confirmations)


def describe() -> dict[str, object]:
    """Ефективний стан для /status, bootstrap-дашборда й audit-паспортів."""
    return {
        "policy": policy() or "(flags)",
        "require_confirm": require_confirm(),
        "auto_trust_learned": auto_trust_learned(),
        "bypass_confirmations": bypass_confirmations(),
    }
