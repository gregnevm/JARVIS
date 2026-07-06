"""Autopilot — OKR-керована стейт-машина самопокращення (R3 «Тонкий шлюз», S3).

Публічний API пакета. Логіка в `core.py` (перенесена дослівно з
`gateway/app/auto_coroutine.py`); критерій §1 спеки:
`from jarvis_core.autopilot import plan_cycle, render_dashboard, run_cycle`.
"""
from .core import (
    STAGE_IDS as STAGE_IDS,
)
from .core import (
    STAGES as STAGES,
)
from .core import (
    CycleResult as CycleResult,
)
from .core import (
    StageContext as StageContext,
)
from .core import (
    StageDispatch as StageDispatch,
)
from .core import (
    StageOutcome as StageOutcome,
)
from .core import _pytest_summary as _pytest_summary  # тести parsers (приватний, свідомо)
from .core import (
    append_run_log as append_run_log,
)
from .core import (
    auto_coroutine_loop as auto_coroutine_loop,
)
from .core import (
    load_okr as load_okr,
)
from .core import (
    make_local_dispatch as make_local_dispatch,
)
from .core import (
    make_tools_dispatch as make_tools_dispatch,
)
from .core import (
    outcome_deltas as outcome_deltas,
)
from .core import (
    plan_cycle as plan_cycle,
)
from .core import (
    render_dashboard as render_dashboard,
)
from .core import (
    run_cycle as run_cycle,
)
from .core import (
    save_dashboard as save_dashboard,
)
from .core import (
    save_okr as save_okr,
)
