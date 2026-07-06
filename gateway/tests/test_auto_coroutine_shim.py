"""R3 «Тонкий шлюз»: shim сумісності auto_coroutine → jarvis_core.autopilot.

Контракт на 1 реліз (план відкату спеки): старі import-шляхи гарантовано живі,
і це та сама логіка, що в ядрі (не копія)."""
from __future__ import annotations


def test_shim_reexports_core_api():
    from app import auto_coroutine as shim

    from jarvis_core import autopilot as core

    for name in (
        "STAGES", "StageContext", "StageOutcome", "CycleResult",
        "plan_cycle", "run_cycle", "render_dashboard",
        "auto_coroutine_loop", "make_tools_dispatch", "make_local_dispatch",
        "load_okr", "save_okr",
    ):
        assert getattr(shim, name) is getattr(core, name), name
