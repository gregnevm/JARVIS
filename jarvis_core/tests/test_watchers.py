"""TC-5 — watchers: overdue-step детектор → read-only notify-пропозиції."""
from __future__ import annotations

from jarvis_core.proactive import overdue_steps, process_watch_proposals
from jarvis_core.proactive.gate import requires_confirmation
from jarvis_core.process import Process, ProcessStep


def _proc(status: str = "running") -> Process:
    return Process(
        id="p1", org_id="o", owner_user_id="A", title="Deal", status=status,
        steps=[
            ProcessStep(id="s1", title="call", assignee_user_id="A", due="2026-01-01T00:00:00"),
            ProcessStep(id="s2", title="send", assignee_user_id="B", due="2099-01-01T00:00:00"),
            ProcessStep(id="s3", title="done step", assignee_user_id="A", due="2026-01-01T00:00:00", status="done"),
        ],
    )


def test_overdue_detects_only_past_nonterminal() -> None:
    assert overdue_steps(_proc(), "2026-06-17T00:00:00") == ["s1"]


def test_proposals_are_readonly_notify() -> None:
    props = process_watch_proposals([_proc()], "2026-06-17T00:00:00")
    assert len(props) == 1
    p = props[0]
    assert p.kind == "notify"
    assert p.meta["step_id"] == "s1"
    assert requires_confirmation(p) is False  # notify — авто (read-only, S4)


def test_skips_non_running_process() -> None:
    assert process_watch_proposals([_proc(status="done")], "2026-06-17T00:00:00") == []
