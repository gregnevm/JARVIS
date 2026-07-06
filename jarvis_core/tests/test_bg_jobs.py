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


# --- numeric-field validation: clean ValueError, not leaked int()/TypeError (P2 fail-fast) ---

def test_int_field_defaults_when_missing():
    # відсутнє числове поле → канонічний дефолт (семантика `or default` збережена)
    assert normalize_payload("deep_research", {"query": "q"})["max_hops"] == 3
    assert normalize_payload("subagent", {"task": "t"})["budget_iters"] == 3
    assert normalize_payload("orchestrator", {"task": "t"}) == {
        "task": "t", "run_id": "", "worker_budget": 5, "max_revisions": 1,
    }


def test_int_field_coerces_numeric_string():
    # числовий рядок з JSON коерситься так само, як робив голий int()
    assert normalize_payload("deep_research", {"query": "q", "max_hops": "7"})["max_hops"] == 7


@pytest.mark.parametrize(
    "job_type,payload,field",
    [
        ("deep_research", {"query": "q", "max_hops": "abc"}, "max_hops"),
        ("subagent", {"task": "t", "budget_iters": "x"}, "budget_iters"),
        ("agent_team", {"task": "t", "budget_per_role": "n"}, "budget_per_role"),
        ("orchestrator", {"task": "t", "worker_budget": "z"}, "worker_budget"),
        ("orchestrator", {"task": "t", "max_revisions": "q"}, "max_revisions"),
        ("coding_task", {"exe": "pytest", "max_rounds": "y"}, "max_rounds"),
    ],
)
def test_non_numeric_int_field_raises_clean_value_error(job_type, payload, field):
    # нечисловий рядок → чистий ValueError із назвою поля, не витік `invalid literal for int()`
    with pytest.raises(ValueError, match=f"{field} must be an integer"):
        normalize_payload(job_type, payload)


@pytest.mark.parametrize(
    "job_type,payload,field",
    [
        ("deep_research", {"query": "q", "max_hops": [1, 2]}, "max_hops"),
        ("subagent", {"task": "t", "budget_iters": {"n": 1}}, "budget_iters"),
    ],
)
def test_non_int_type_raises_value_error_not_typeerror(job_type, payload, field):
    # list/dict раніше давали TypeError, що прослизав повз `except ValueError` у роутах → 500.
    # тепер це чистий ValueError (→ 400) із назвою поля.
    with pytest.raises(ValueError, match=f"{field} must be an integer"):
        normalize_payload(job_type, payload)
