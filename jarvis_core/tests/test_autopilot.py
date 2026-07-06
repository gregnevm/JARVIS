"""Auto-coroutine: plan_cycle/outcome_deltas (чисті), run_cycle (фейк-dispatch),
сховище OKR + run-log, render_dashboard, прод-dispatch (фейк ToolsClient)."""
from __future__ import annotations

import pytest

from jarvis_core.autopilot import (
    STAGE_IDS,
    StageContext,
    StageOutcome,
    _pytest_summary,
    append_run_log,
    load_okr,
    make_local_dispatch,
    make_tools_dispatch,
    outcome_deltas,
    plan_cycle,
    render_dashboard,
    run_cycle,
    save_okr,
)
from jarvis_core.okr import OKR, KeyResult, Objective


def _okr(*progress: float) -> OKR:
    krs = tuple(KeyResult(id=f"k{i}", text=f"k{i}", progress=p) for i, p in enumerate(progress))
    return OKR(objectives=(Objective(id="O", title="Obj", roadmap="ROADMAP.md", key_results=krs),))


# --- plan_cycle / outcome_deltas ---

def test_plan_cycle_returns_actionable_objective():
    assert plan_cycle(_okr(0.0)).id == "O"


def test_plan_cycle_none_when_met():
    assert plan_cycle(_okr(1.0)) is None


def test_outcome_deltas_explicit_kr_progress_summed():
    obj = _okr(0.0).objectives[0]
    outs = [StageOutcome(True, "a", kr_progress={"k0": 0.2}), StageOutcome(True, "b", kr_progress={"k0": 0.1})]
    assert outcome_deltas(obj, outs)["k0"] == pytest.approx(0.3)


def test_outcome_deltas_implicit_push_to_least_progressed_open_kr():
    obj = _okr(0.5, 0.1).objectives[0]  # k1 least progressed, open
    outs = [StageOutcome(True, "ok"), StageOutcome(True, "ok"), StageOutcome(False, "bad")]
    deltas = outcome_deltas(obj, outs)
    assert set(deltas) == {"k1"}
    assert deltas["k1"] == 0.10  # 2 ok stages * 0.05


def test_outcome_deltas_no_open_kr_no_implicit():
    obj = _okr(1.0).objectives[0]
    assert outcome_deltas(obj, [StageOutcome(True, "ok")]) == {}


# --- run_cycle ---

async def test_run_cycle_dispatches_five_stages_and_evolves():
    calls: list[str] = []

    async def fake_dispatch(ctx: StageContext) -> StageOutcome:
        calls.append(ctx.stage)
        return StageOutcome(ok=True, summary=f"did {ctx.stage}")

    okr = _okr(0.0)
    new_okr, result = await run_cycle(okr, fake_dispatch, user_id=42, repo_path=".")
    # evolve не диспатчиться — це мутація тут-таки
    assert calls == ["code", "review", "refactor", "analyze", "test"]
    assert [s for s, _, _ in result.stages] == list(STAGE_IDS)
    assert new_okr.cycle == 1
    assert new_okr.objectives[0].key_results[0].progress > 0  # просунулись


async def test_run_cycle_none_when_no_objective():
    okr = _okr(1.0)
    new_okr, result = await run_cycle(okr, _raise_dispatch, user_id=1, repo_path=".")
    assert result is None
    assert new_okr is okr


async def test_run_cycle_failing_stage_does_not_break_cycle():
    async def boom(ctx: StageContext) -> StageOutcome:
        if ctx.stage == "review":
            raise RuntimeError("nope")
        return StageOutcome(ok=True, summary="ok")

    _, result = await run_cycle(_okr(0.0), boom, user_id=1, repo_path=".")
    review = next(r for r in result.stages if r[0] == "review")
    assert review[1] is False  # помічено як fail, цикл доїхав


async def _raise_dispatch(ctx: StageContext) -> StageOutcome:  # pragma: no cover
    raise AssertionError("should not dispatch when no objective")


# --- store IO + run-log ---

def test_load_save_okr_round_trip(tmp_path):
    save_okr(str(tmp_path), _okr(0.4))
    loaded = load_okr(str(tmp_path))
    assert loaded.objectives[0].key_results[0].progress == 0.4


def test_load_okr_missing_returns_empty(tmp_path):
    assert load_okr(str(tmp_path)).objectives == ()


async def test_append_run_log_writes_markdown(tmp_path):
    _, result = await run_cycle(_okr(0.0), _ok_dispatch, user_id=1, repo_path=".")
    append_run_log(str(tmp_path), result)
    text = (tmp_path / "autopilot" / "run_log.md").read_text(encoding="utf-8")
    assert "Cycle @" in text and "**code**" in text


async def _ok_dispatch(ctx: StageContext) -> StageOutcome:
    return StageOutcome(ok=True, summary="ok")


# --- dashboard ---

def test_render_dashboard_contains_objective_and_admin_context():
    okr = OKR(
        objectives=(Objective(id="O", title="Obj", priority=1, key_results=(KeyResult("k", "KR", progress=0.5),)),),
        admin_context="focus O",
        cycle=3,
    )
    md = render_dashboard(okr, [])
    assert "Autopilot" in md and "`O`" in md and "Admin context" in md and "Цикл:** 3" in md


def test_render_dashboard_mode_reflects_bypass_flag():
    okr = OKR(objectives=(Objective(id="O", title="Obj"),))
    assert "🔒 Supervised" in render_dashboard(okr, [])
    assert "🔓 Bypass permissions" in render_dashboard(okr, [], bypass=True)


def test_render_dashboard_mode_reflects_ultracode_flag():
    okr = OKR(objectives=(Objective(id="O", title="Obj"),))
    assert "ULTRACODE" not in render_dashboard(okr, [], bypass=True)
    md = render_dashboard(okr, [], bypass=True, ultracode=True)
    assert "🔓 Bypass permissions" in md and "⚡ ULTRACODE" in md


def test_save_dashboard_bypass_persists_mode(tmp_path):
    from jarvis_core.autopilot import save_dashboard

    okr = OKR(objectives=(Objective(id="O", title="Obj"),))
    save_dashboard(str(tmp_path), okr, [], bypass=True)
    text = (tmp_path / "autopilot" / "dashboard.md").read_text(encoding="utf-8")
    assert "🔓 Bypass permissions" in text


# --- production dispatch over a fake ToolsClient ---

class FakeTools:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def spawn_orchestrator(self, uid, task, *, worker_budget=5):
        self.seen.append(f"orchestrate:{task[:10]}")
        return {"run_id": "r1"}

    async def improve_scan(self, uid):
        self.seen.append("scan")
        return {"items": [1, 2]}

    async def repo_tree(self, uid):
        self.seen.append("tree")
        return {"tree": "a/\n  b.py"}

    async def create_coding_job(self, uid, exe, *, path="", task=""):
        self.seen.append(f"coding:{exe}")
        return {"job_id": "j1"}


async def test_make_tools_dispatch_routes_each_stage():
    tools = FakeTools()
    dispatch = make_tools_dispatch(tools)
    obj = _okr(0.0).objectives[0]
    for stage in ("code", "review", "refactor", "analyze", "test"):
        out = await dispatch(StageContext(objective=obj, stage=stage, user_id=7, repo_path="."))
        assert out.ok, stage
    assert "scan" in tools.seen
    assert "coding:pytest" in tools.seen
    assert any(s.startswith("orchestrate:") for s in tools.seen)


# --- _pytest_summary ---

def test_pytest_summary_parses_status_line():
    out = "....\n==================== 15 passed in 0.04s ====================\n"
    assert _pytest_summary(out, 0) == "15 passed in 0.04s"


def test_pytest_summary_parses_mixed_counts_without_status_bar():
    out = "FF..\n1 failed 3 passed somewhere\n"
    assert _pytest_summary(out, 1) == "1 failed, 3 passed"


def test_pytest_summary_falls_back_to_exit_code():
    assert _pytest_summary("...........  [100%]\n", 0) == "усі зелені"
    assert _pytest_summary("collection error", 2) == "впав (exit 2)"


# --- make_local_dispatch (non-subprocess stages) ---

async def test_local_dispatch_code_and_refactor_are_planned_ok():
    dispatch = make_local_dispatch(".")
    obj = _okr(0.0).objectives[0]
    for stage in ("code", "refactor"):
        out = await dispatch(StageContext(objective=obj, stage=stage, user_id=1, repo_path="."))
        assert out.ok and "план" in out.summary


async def test_local_dispatch_analyze_snapshots_repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("x = 1\n")
    dispatch = make_local_dispatch(str(tmp_path))
    obj = _okr(0.0).objectives[0]
    out = await dispatch(StageContext(objective=obj, stage="analyze", user_id=1, repo_path=str(tmp_path)))
    assert out.ok and "py-файл" in out.summary and "pkg" in out.artifact


async def test_dispatch_marks_error_outcome():
    class Failing(FakeTools):
        async def improve_scan(self, uid):
            return {"error": "tools down"}

    dispatch = make_tools_dispatch(Failing())
    obj = _okr(0.0).objectives[0]
    out = await dispatch(StageContext(objective=obj, stage="review", user_id=1, repo_path="."))
    assert out.ok is False and "tools down" in out.summary


class CapturingTools(FakeTools):
    def __init__(self) -> None:
        super().__init__()
        self.budgets: list[int] = []
        self.tasks: list[str] = []

    async def spawn_orchestrator(self, uid, task, *, worker_budget=5):
        self.budgets.append(worker_budget)
        self.tasks.append(task)
        return {"run_id": "r1"}


async def test_ultracode_bumps_budget_and_frames_prompt():
    tools = CapturingTools()
    obj = _okr(0.0).objectives[0]
    ctx = StageContext(objective=obj, stage="code", user_id=7, repo_path=".")

    await make_tools_dispatch(tools, worker_budget=4)(ctx)
    assert tools.budgets[-1] == 4 and "[ULTRACODE]" not in tools.tasks[-1]

    await make_tools_dispatch(tools, worker_budget=4, ultracode=True)(ctx)
    assert tools.budgets[-1] == 8 and tools.tasks[-1].startswith("[ULTRACODE]")
