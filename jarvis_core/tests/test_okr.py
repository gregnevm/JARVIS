"""OKR-модель: progress/done, select_objective, mutate_okr, (де)серіалізація."""
from __future__ import annotations

from jarvis_core.okr import (
    KeyResult,
    OKR,
    Objective,
    mutate_okr,
    okr_from_dict,
    okr_to_dict,
    select_objective,
)


def _kr(id_: str, progress: float = 0.0, target: float = 1.0) -> KeyResult:
    return KeyResult(id=id_, text=id_, progress=progress, target=target)


def _obj(id_: str, priority: int = 3, krs: tuple[KeyResult, ...] = (), status: str = "active") -> Objective:
    return Objective(id=id_, title=id_, priority=priority, status=status, key_results=krs)


# --- KeyResult / Objective progress ---

def test_kr_ratio_clamped():
    assert _kr("a", progress=5.0, target=2.0).ratio == 1.0
    assert _kr("a", progress=1.0, target=2.0).ratio == 0.5


def test_kr_done_threshold():
    assert _kr("a", progress=1.0).done
    assert not _kr("a", progress=0.99).done


def test_objective_progress_average_of_krs():
    obj = _obj("O", krs=(_kr("a", 1.0), _kr("b", 0.0)))
    assert obj.progress == 0.5
    assert not obj.is_met


def test_objective_met_when_all_krs_done():
    obj = _obj("O", krs=(_kr("a", 1.0), _kr("b", 1.0)))
    assert obj.is_met


def test_objective_without_krs_not_met():
    assert not _obj("O").is_met


# --- select_objective ---

def test_select_skips_done_and_paused():
    okr = OKR(objectives=(
        _obj("done", krs=(_kr("x", 1.0),)),
        _obj("paused", status="paused", krs=(_kr("y", 0.0),)),
        _obj("live", krs=(_kr("z", 0.0),)),
    ))
    assert select_objective(okr).id == "live"


def test_select_prefers_lower_priority_number():
    okr = OKR(objectives=(
        _obj("low", priority=4, krs=(_kr("a", 0.0),)),
        _obj("high", priority=1, krs=(_kr("b", 0.0),)),
    ))
    assert select_objective(okr).id == "high"


def test_select_breaks_ties_by_least_progress():
    okr = OKR(objectives=(
        _obj("ahead", priority=2, krs=(_kr("a", 0.8),)),
        _obj("behind", priority=2, krs=(_kr("b", 0.1),)),
    ))
    assert select_objective(okr).id == "behind"


def test_select_none_when_all_met():
    okr = OKR(objectives=(_obj("o", krs=(_kr("a", 1.0),)),))
    assert select_objective(okr) is None


# --- mutate_okr ---

def test_mutate_applies_kr_deltas_with_clip():
    okr = OKR(objectives=(_obj("O", krs=(_kr("a", 0.9),)),))
    out = mutate_okr(okr, kr_deltas={"a": 0.5})
    assert out.objectives[0].key_results[0].progress == 1.0  # clipped to target
    assert out.cycle == 1


def test_mutate_marks_objective_done_when_krs_complete():
    okr = OKR(objectives=(_obj("O", krs=(_kr("a", 0.9),)),))
    out = mutate_okr(okr, kr_deltas={"a": 0.2})
    assert out.objectives[0].status == "done"


def test_mutate_admin_context_boosts_priority_by_id():
    okr = OKR(objectives=(_obj("PLT", priority=3, krs=(_kr("a", 0.0),)),))
    out = mutate_okr(okr, admin_context="зосередься на PLT цьому тижні")
    assert out.objectives[0].priority == 2
    assert out.admin_context.startswith("зосередься")


def test_mutate_admin_context_preserved_when_none():
    okr = OKR(objectives=(), admin_context="keep me")
    out = mutate_okr(okr, admin_context=None)
    assert out.admin_context == "keep me"


def test_mutate_does_not_boost_paused_objective():
    okr = OKR(objectives=(_obj("X", priority=3, status="paused", krs=(_kr("a", 0.0),)),))
    out = mutate_okr(okr, admin_context="X please")
    assert out.objectives[0].priority == 3


# --- round-trip ---

def test_serialization_round_trip():
    okr = OKR(
        objectives=(_obj("O", priority=2, krs=(_kr("a", 0.3), _kr("b", 1.0))),),
        admin_context="ctx",
        cycle=4,
    )
    again = okr_from_dict(okr_to_dict(okr))
    assert again.cycle == 4
    assert again.admin_context == "ctx"
    assert again.objectives[0].priority == 2
    assert again.objectives[0].key_results[1].done
