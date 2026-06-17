import pytest

from jarvis_core.bg_jobs import JOB_TYPES, normalize_payload, platform_create_method


def test_job_types_complete():
    assert "agent_turn" in JOB_TYPES
    assert "coding_task" in JOB_TYPES
    assert "delegate_tick" in JOB_TYPES
    assert len(JOB_TYPES) == 8


def test_normalize_delegate_tick():
    out = normalize_payload("delegate_tick", {"principal_id": "A", "org_id": "o", "cursor": "c1"})
    assert out == {"principal_id": "A", "org_id": "o", "cursor": "c1"}


def test_normalize_delegate_tick_requires_principal():
    import pytest

    with pytest.raises(ValueError):
        normalize_payload("delegate_tick", {"org_id": "o"})


def test_platform_create_method_mapping():
    assert platform_create_method("deep_research") == "create_research_job"
    assert platform_create_method("cursor_task") == "create_cursor_job"
    assert platform_create_method("coding_task") == "create_coding_job"
    assert platform_create_method("agent_turn") == "create_bg_job"
    assert platform_create_method("subagent") == "create_bg_job"


def test_normalize_agent_turn():
    out = normalize_payload("agent_turn", {"text": "hello", "mode": "chat"})
    assert out == {"text": "hello", "mode": "chat"}


def test_normalize_agent_turn_requires_text():
    with pytest.raises(ValueError, match="text required"):
        normalize_payload("agent_turn", {"text": "  "})


def test_normalize_deep_research():
    out = normalize_payload("deep_research", {"query": "topic", "max_hops": 2})
    assert out == {"query": "topic", "max_hops": 2}


def test_normalize_subagent():
    out = normalize_payload("subagent", {"task": "analyze", "budget_iters": 4})
    assert out["task"] == "analyze"
    assert out["budget_iters"] == 4


def test_normalize_coding_task():
    out = normalize_payload(
        "coding_task",
        {"exe": "pytest", "args": ["-q", "tests/"], "path": "/repo", "max_rounds": 3},
    )
    assert out["exe"] == "pytest" and out["args"] == ["-q", "tests/"]
    assert out["path"] == "/repo" and out["max_rounds"] == 3


def test_normalize_coding_task_requires_exe():
    with pytest.raises(ValueError, match="exe required"):
        normalize_payload("coding_task", {"args": ["-q"]})


def test_normalize_unknown_type():
    with pytest.raises(ValueError, match="unknown job type"):
        normalize_payload("bogus", {"text": "x"})
