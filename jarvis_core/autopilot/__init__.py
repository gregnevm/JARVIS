"""Autopilot — OKR-керована стейт-машина самопокращення (R3 «Тонкий шлюз», S3).

Публічний API пакета. Логіка в `core.py` (перенесена дослівно з
`gateway/app/auto_coroutine.py`); критерій §1 спеки:
`from jarvis_core.autopilot import plan_cycle, render_dashboard, run_cycle`.
"""
from .core import (
    STAGE_IDS as STAGE_IDS,
    STAGES as STAGES,
    CycleResult as CycleResult,
    StageContext as StageContext,
    StageDispatch as StageDispatch,
    StageOutcome as StageOutcome,
    append_run_log as append_run_log,
    auto_coroutine_loop as auto_coroutine_loop,
    load_okr as load_okr,
    make_local_dispatch as make_local_dispatch,
    make_tools_dispatch as make_tools_dispatch,
    outcome_deltas as outcome_deltas,
    plan_cycle as plan_cycle,
    render_dashboard as render_dashboard,
    run_cycle as run_cycle,
    save_dashboard as save_dashboard,
    save_okr as save_okr,
)
from .core import _pytest_summary as _pytest_summary  # тести parsers (приватний, свідомо)
