"""Shim сумісності (R3 «Тонкий шлюз»): логіка переїхала в `jarvis_core.autopilot`.

Стейт-машина автопілота — чиста логіка без gateway-залежностей, тепер живе в ядрі
(S3: gateway — лише канал/IO). Цей модуль лишається на 1 реліз для сумісності
import-шляхів у проді (план відкату зі спеки docs/REFACTOR_THIN_GATEWAY.spec.md);
нові імпорти — напряму з `jarvis_core.autopilot`.
"""
from jarvis_core.autopilot import (
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
