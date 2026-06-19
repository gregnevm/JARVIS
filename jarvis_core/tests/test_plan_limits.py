"""Plan-limits політика (AP-4.3) — SSOT квот по планах + чиста перевірка `exceeds`."""
import pytest

from jarvis_core.context import VALID_PLANS, synthetic_context
from jarvis_core.plan_limits import (
    PLAN_LIMITS,
    RESOURCES,
    UNLIMITED,
    PlanLimits,
    exceeds,
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
