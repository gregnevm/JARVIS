"""TEAM_ECOSYSTEM TC-5 — S4-гейт проактивних дій делегата."""
from __future__ import annotations

from jarvis_core.proactive import ProposedAction, gate_actions, requires_confirmation


def test_read_only_is_auto() -> None:
    a = ProposedAction(kind="summarize", summary="daily brief")
    assert requires_confirmation(a) is False


def test_external_always_confirms_even_with_scope() -> None:
    a = ProposedAction(kind="send", summary="email client", external=True)
    assert requires_confirmation(a, {"act:auto"}) is True


def test_money_and_irreversible_confirm() -> None:
    assert requires_confirmation(ProposedAction(kind="pay", summary="invoice", money=True)) is True
    assert requires_confirmation(ProposedAction(kind="delete", summary="drop", irreversible=True)) is True


def test_mutating_needs_scope_for_auto() -> None:
    a = ProposedAction(kind="update", summary="set status", mutating=True)
    assert requires_confirmation(a) is True                  # без scope → confirm
    assert requires_confirmation(a, {"act:auto"}) is False   # зі scope → auto


def test_gate_partitions() -> None:
    actions = [
        ProposedAction(kind="draft", summary="reply draft"),
        ProposedAction(kind="send", summary="send reply", external=True),
        ProposedAction(kind="update", summary="status", mutating=True),
    ]
    auto, confirm = gate_actions(actions, {"act:auto"})
    assert [a.summary for a in auto] == ["reply draft", "status"]
    assert [a.summary for a in confirm] == ["send reply"]
