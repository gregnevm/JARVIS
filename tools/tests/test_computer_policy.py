"""Approval-драбина: матриця політик, back-compat прапорів, fail-closed невідомого."""
from __future__ import annotations

import pytest
from app import computer_policy
from app.config import settings


def test_unset_policy_falls_back_to_flags(monkeypatch):
    monkeypatch.setattr(settings, "computer_approval_policy", "")
    monkeypatch.setattr(settings, "computer_require_confirm", False)
    monkeypatch.setattr(settings, "computer_auto_trust_learned", False)
    monkeypatch.setattr(settings, "bypass_confirmations", True)
    assert computer_policy.policy() == ""
    assert computer_policy.require_confirm() is False
    assert computer_policy.auto_trust_learned() is False
    assert computer_policy.bypass_confirmations() is True


@pytest.mark.parametrize(
    "name,confirm,trust,bypass",
    [
        ("strict", True, False, False),
        ("smart", True, True, False),
        ("auto", False, True, False),
        ("off", False, True, True),
    ],
)
def test_policy_matrix_overrides_flags(monkeypatch, name, confirm, trust, bypass):
    # прапори виставлені «навпаки» — політика мусить перекрити всі (SSOT, P7)
    monkeypatch.setattr(settings, "computer_approval_policy", name)
    monkeypatch.setattr(settings, "computer_require_confirm", not confirm)
    monkeypatch.setattr(settings, "computer_auto_trust_learned", not trust)
    monkeypatch.setattr(settings, "bypass_confirmations", not bypass)
    assert computer_policy.require_confirm() is confirm
    assert computer_policy.auto_trust_learned() is trust
    assert computer_policy.bypass_confirmations() is bypass


def test_unknown_policy_fails_closed_to_strict(monkeypatch):
    monkeypatch.setattr(settings, "computer_approval_policy", "yolo")
    assert computer_policy.policy() == "strict"
    assert computer_policy.require_confirm() is True
    assert computer_policy.bypass_confirmations() is False


def test_policy_normalization(monkeypatch):
    monkeypatch.setattr(settings, "computer_approval_policy", "  SMART ")
    assert computer_policy.policy() == "smart"


def test_describe_shape(monkeypatch):
    monkeypatch.setattr(settings, "computer_approval_policy", "")
    d = computer_policy.describe()
    assert d["policy"] == "(flags)"
    assert set(d) == {"policy", "require_confirm", "auto_trust_learned", "bypass_confirmations"}


def test_strict_disables_learned_trust_end_to_end(monkeypatch):
    """strict вимикає auto-trust навіть якщо cmdlet у learned-whitelist."""
    from app import computer_learned

    monkeypatch.setattr(settings, "computer_approval_policy", "strict")
    monkeypatch.setattr(computer_learned, "learned_ps", lambda: {"get-date"})
    assert computer_learned.is_ps_trusted("Get-Date") is False
    monkeypatch.setattr(settings, "computer_approval_policy", "smart")
    assert computer_learned.is_ps_trusted("Get-Date") is True
