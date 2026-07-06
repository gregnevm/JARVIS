"""Shim сумісності (R3 «Тонкий шлюз»): логіка переїхала в `jarvis_core.autopilot`.

Стейт-машина автопілота — чиста логіка без gateway-залежностей, тепер живе в ядрі
(S3: gateway — лише канал/IO). Цей модуль лишається на 1 реліз для сумісності
import-шляхів у проді (план відкату зі спеки docs/REFACTOR_THIN_GATEWAY.spec.md);
нові імпорти — напряму з `jarvis_core.autopilot`.
"""
from jarvis_core.autopilot import (
    STAGE_IDS as STAGE_IDS,
)
from jarvis_core.autopilot import (
    STAGES as STAGES,
)
from jarvis_core.autopilot import (
    CycleResult as CycleResult,
)
from jarvis_core.autopilot import (
    StageContext as StageContext,
)
from jarvis_core.autopilot import (
    StageDispatch as StageDispatch,
)
from jarvis_core.autopilot import (
    StageOutcome as StageOutcome,
)
from jarvis_core.autopilot import (
    append_run_log as append_run_log,
)
from jarvis_core.autopilot import (
    auto_coroutine_loop as auto_coroutine_loop,
)
from jarvis_core.autopilot import (
    load_okr as load_okr,
)
from jarvis_core.autopilot import (
    make_local_dispatch as make_local_dispatch,
)
from jarvis_core.autopilot import (
    make_tools_dispatch as make_tools_dispatch,
)
from jarvis_core.autopilot import (
    outcome_deltas as outcome_deltas,
)
from jarvis_core.autopilot import (
    plan_cycle as plan_cycle,
)
from jarvis_core.autopilot import (
    render_dashboard as render_dashboard,
)
from jarvis_core.autopilot import (
    run_cycle as run_cycle,
)
from jarvis_core.autopilot import (
    save_dashboard as save_dashboard,
)
from jarvis_core.autopilot import (
    save_okr as save_okr,
)
