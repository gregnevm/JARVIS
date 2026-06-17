"""TEAM_ECOSYSTEM TC-6 — Process engine (машина станів, чистий домен)."""
from __future__ import annotations

from jarvis_core.process import (
    Process,
    ProcessStep,
    advance,
    escalation_target,
    is_complete,
    ready_steps,
)


def _proc() -> Process:
    return Process(
        id="p1", org_id="o", owner_user_id="A", title="Onboarding",
        steps=[
            ProcessStep(id="s1", title="Collect docs", assignee_user_id="A", kind="human_task"),
            ProcessStep(id="s2", title="Approve", assignee_user_id="M", kind="approval", depends_on=["s1"]),
            ProcessStep(id="s3", title="Notify", assignee_user_id="A", kind="notify", depends_on=["s2"]),
        ],
    )


def test_ready_steps_respects_dependencies() -> None:
    p = _proc()
    ready = ready_steps(p)
    assert [s.id for s in ready] == ["s1"]  # s2,s3 заблоковані залежностями


def test_advance_unblocks_next() -> None:
    p = _proc()
    assert advance(p, "s1", "done") is True
    assert [s.id for s in ready_steps(p)] == ["s2"]
    assert p.status == "running"  # draft → running після першого переходу


def test_advance_invalid_status_or_step() -> None:
    p = _proc()
    assert advance(p, "s1", "bogus") is False
    assert advance(p, "nope", "done") is False
    assert advance(p, "s1", "pending") is False  # без зміни


def test_skipped_counts_as_satisfied() -> None:
    p = _proc()
    advance(p, "s1", "skipped")
    assert [s.id for s in ready_steps(p)] == ["s2"]


def test_process_completes_when_all_terminal() -> None:
    p = _proc()
    advance(p, "s1", "done")
    advance(p, "s2", "done")
    advance(p, "s3", "done")
    assert is_complete(p) is True
    assert p.status == "done"


def test_cancelled_status_sticky() -> None:
    p = _proc()
    p.status = "cancelled"
    advance(p, "s1", "done")
    assert p.status == "cancelled"  # не воскресає в running


def test_escalation_target() -> None:
    p = _proc()
    assert escalation_target(p, p.steps[1], ["M", "VP"]) == "M"
    assert escalation_target(p, p.steps[1], []) is None


def test_roundtrip_serialization() -> None:
    p = _proc()
    advance(p, "s1", "done")
    restored = Process.from_dict(p.to_dict())
    assert restored.status == "running"
    assert restored.steps[0].status == "done"
    assert restored.steps[1].depends_on == ["s1"]
