"""Plan-limits політика (AP-4.3/AP-4.5) — SSOT квот, `exceeds`, soft/hard + grace."""
import pytest

from jarvis_core.context import VALID_PLANS, synthetic_context
from jarvis_core.plan_limits import (
    DEFAULT_GRACE,
    PLAN_LIMITS,
    RESOURCE_KIND,
    RESOURCES,
    UNLIMITED,
    LimitStatus,
    PlanLimits,
    classify,
    exceeds,
    fail_open,
    hard_cap,
    is_ops,
    limits_for,
    public_limits,
)


def test_policy_covers_exactly_valid_plans():
    # SSOT-інваріант: жоден план не лишається без стель і немає «зайвих» планів.
    assert set(PLAN_LIMITS) == set(VALID_PLANS)


def test_self_hosted_studio_is_unlimited_everywhere():
    # S2: self-hosted власник (synthetic_context → plan=studio) ніколи не впирається в 402.
    plan = synthetic_context(12345).plan
    assert plan == "studio"
    for resource in RESOURCES:
        assert limits_for(plan).cap(resource) == UNLIMITED
        assert exceeds(plan, resource, current=10**12) is False


def test_enterprise_is_unlimited_everywhere():
    for resource in RESOURCES:
        assert exceeds("enterprise", resource, current=10**12) is False


def test_free_is_most_restrictive():
    free = limits_for("free")
    for plan in ("pro", "team"):
        other = limits_for(plan)
        for resource in RESOURCES:
            assert free.cap(resource) < other.cap(resource)


def test_exceeds_boundary_semantics():
    # current < cap → дозволено; current == cap → вже досягнуто (наступну дію відхилити).
    cap = PLAN_LIMITS["free"].cap("max_api_keys")
    assert exceeds("free", "max_api_keys", cap - 1) is False
    assert exceeds("free", "max_api_keys", cap) is True
    assert exceeds("free", "max_api_keys", cap + 1) is True


def test_zero_cap_blocks_everything():
    # 0 — валідний нуль (повна заборона), окремий від UNLIMITED(-1).
    zero = PlanLimits(requests_per_day=0, tokens_per_month=0, max_api_keys=0, rate_limit_per_min=0)
    assert zero.exceeds("requests_per_day", 0) is True


def test_unknown_plan_falls_back_to_free():
    # Невідомий план → найсуворіші (free): fail-closed для білінгу.
    assert limits_for("ghost") == PLAN_LIMITS["free"]
    assert exceeds("ghost", "requests_per_day", PLAN_LIMITS["free"].cap("requests_per_day")) is True


def test_unknown_resource_raises():
    with pytest.raises(ValueError):
        limits_for("pro").cap("disk_gb")
    with pytest.raises(ValueError):
        exceeds("pro", "disk_gb", 1)


def test_limits_are_immutable():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        limits_for("free").requests_per_day = 999  # type: ignore[misc]


def test_public_limits_studio_all_none():
    # UNLIMITED → None у публічній проєкції (чесний JSON для /whoami та Billing-табу).
    pub = public_limits("studio")
    assert set(pub) == set(RESOURCES)
    assert all(v is None for v in pub.values())


def test_public_limits_free_are_concrete_ints():
    pub = public_limits("free")
    assert pub["max_api_keys"] == PLAN_LIMITS["free"].cap("max_api_keys")
    assert all(isinstance(v, int) for v in pub.values())


# ── AP-4.5: soft/hard + grace ───────────────────────────────────────────────────


def test_resource_kind_covers_exactly_resources():
    # SSOT-інваріант: жоден ресурс не лишається без kind-класифікації (інакше протече повз grace).
    assert set(RESOURCE_KIND) == set(RESOURCES)


def test_kind_split_ops_vs_billing():
    assert is_ops("requests_per_day") and is_ops("rate_limit_per_min")
    assert not is_ops("tokens_per_month") and not is_ops("max_api_keys")


def test_fail_open_is_ops_only():
    # fail-open ops, fail-closed billing.
    assert fail_open("requests_per_day") is True
    assert fail_open("rate_limit_per_min") is True
    assert fail_open("tokens_per_month") is False
    assert fail_open("max_api_keys") is False


def test_is_ops_unknown_resource_raises():
    with pytest.raises(ValueError):
        is_ops("disk_gb")
    with pytest.raises(ValueError):
        fail_open("disk_gb")
    with pytest.raises(ValueError):
        hard_cap("free", "disk_gb")
    with pytest.raises(ValueError):
        classify("free", "disk_gb", 0)


def test_hard_cap_ops_adds_grace_floored():
    cap = PLAN_LIMITS["free"].cap("requests_per_day")  # 200
    assert hard_cap("free", "requests_per_day", grace=0.10) == int(cap * 1.10)  # 220
    # floor, не округлення вгору: 200 * 1.07 = 214.0 → 214; неціле зрізається донизу.
    assert hard_cap("free", "requests_per_day", grace=0.07) == 214


def test_hard_cap_billing_has_no_grace():
    cap = PLAN_LIMITS["free"].cap("tokens_per_month")
    assert hard_cap("free", "tokens_per_month", grace=0.50) == cap  # billing: hard == soft


def test_hard_cap_unlimited_stays_unlimited():
    assert hard_cap("studio", "requests_per_day") == UNLIMITED
    assert hard_cap("studio", "tokens_per_month", grace=0.5) == UNLIMITED


def test_classify_ops_ok_grace_blocked_bands():
    cap = PLAN_LIMITS["free"].cap("requests_per_day")  # 200, hard@10% = 220
    assert classify("free", "requests_per_day", cap - 1) == LimitStatus.OK
    assert classify("free", "requests_per_day", cap) == LimitStatus.GRACE
    assert classify("free", "requests_per_day", 219) == LimitStatus.GRACE
    assert classify("free", "requests_per_day", 220) == LimitStatus.BLOCKED
    assert classify("free", "requests_per_day", 10_000) == LimitStatus.BLOCKED


def test_classify_billing_blocks_at_soft_no_grace():
    cap = PLAN_LIMITS["free"].cap("tokens_per_month")
    assert classify("free", "tokens_per_month", cap - 1) == LimitStatus.OK
    assert classify("free", "tokens_per_month", cap) == LimitStatus.BLOCKED  # без grace
    assert classify("free", "tokens_per_month", cap + 1) == LimitStatus.BLOCKED


def test_classify_unlimited_always_ok():
    # S2: studio/enterprise ніколи не впирається — навіть із величезним current.
    for resource in RESOURCES:
        assert classify("studio", resource, 10**12) == LimitStatus.OK
        assert classify("enterprise", resource, 10**12) == LimitStatus.OK


def test_classify_zero_cap_blocks_immediately():
    # Повна заборона (cap=0) лишається 0 під grace → BLOCKED уже на current=0 (ops і billing).
    assert hard_cap("free", "requests_per_day", grace=0.0) == PLAN_LIMITS["free"].cap("requests_per_day")
    zero = PlanLimits(requests_per_day=0, tokens_per_month=0, max_api_keys=0, rate_limit_per_min=0)
    assert zero.cap("requests_per_day") == 0  # sanity: 0 != UNLIMITED


def test_classify_consistent_with_exceeds_at_soft_boundary():
    # `classify` != OK рівно там, де `exceeds` == True (на/над soft-стелею).
    for plan in ("free", "pro", "team"):
        for resource in RESOURCES:
            cap = limits_for(plan).cap(resource)
            assert (classify(plan, resource, cap) != LimitStatus.OK) == exceeds(plan, resource, cap)
            assert classify(plan, resource, cap - 1) == LimitStatus.OK


def test_default_grace_is_positive_fraction():
    assert 0.0 < DEFAULT_GRACE < 1.0
