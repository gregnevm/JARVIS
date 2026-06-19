"""Plan limits — політика квот на план (AP-4.3, SAAS_DEEP_DIVE §0.2/§9).

SSOT мапінгу «план → ліміти ресурсу». Чистий: лише дані + чисті перевірки, без Redis і
без HTTP. Лічення фактичного usage живе у gateway (`saas/usage.py`), а enforcement (`402`)
підключає цю політику в request-path окремо (AP-4.5) — тут лише *скільки можна*.

Дім модуля — `jarvis_core/`, поряд із `VALID_PLANS` у [`context.py`](context.py):
це P7 (Single Source of Truth) і дисципліна multi-tenant (білінгова/tenant-логіка живе
в core, не дублюється gateway↔tools — AGENTS.md §5).

Семантика:
  * `UNLIMITED` (`-1`) — без стелі. `studio`/`enterprise` мають його на всіх ресурсах:
    self-hosted власник за замовчуванням `studio` (див. `synthetic_context`), і принцип S2
    («self-hosted ніколи не ламається») вимагає, щоб він **ніколи** не впирався в `402`.
  * `exceeds(plan, resource, current)` — `True`, коли поточний показник досяг стелі
    (`current >= cap`), тобто **наступну** дію слід відхилити (`402`). `UNLIMITED` → завжди `False`.
  * Невідомий план → ліміти `free` (найсуворіші): fail-closed для білінгу. Self-hosted
    передає валідний `studio`, тож у нього fallback не спрацьовує.
  * Невідомий ресурс → `ValueError` (fail-fast, P3 — явні межі, не «магічні рядки»).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .context import VALID_PLANS

# Стеля «без обмежень» — окреме значення, щоб 0 лишався валідним нулем (повна заборона).
UNLIMITED = -1

# Канонічний перелік ресурсів, які квотуються (адресуються по імені поля `PlanLimits`).
RESOURCES = ("requests_per_day", "tokens_per_month", "max_api_keys", "rate_limit_per_min")


@dataclass(frozen=True)
class PlanLimits:
    """Стелі одного плану. `UNLIMITED` (`-1`) = без обмеження; `0` = повна заборона."""

    requests_per_day: int
    tokens_per_month: int
    max_api_keys: int
    rate_limit_per_min: int

    def cap(self, resource: str) -> int:
        """Стеля ресурсу. Невідомий ресурс → `ValueError` (fail-fast)."""
        if resource not in RESOURCES:
            raise ValueError(f"unknown resource: {resource!r}")
        return int(getattr(self, resource))

    def exceeds(self, resource: str, current: int) -> bool:
        """`True`, якщо `current` досяг стелі ресурсу (наступну дію відхилити)."""
        cap = self.cap(resource)
        if cap == UNLIMITED:
            return False
        return current >= cap


# Політика по планах. `studio`/`enterprise` — UNLIMITED (S2: self-hosted не впирається в 402).
PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        requests_per_day=200,
        tokens_per_month=100_000,
        max_api_keys=2,
        rate_limit_per_min=20,
    ),
    "pro": PlanLimits(
        requests_per_day=5_000,
        tokens_per_month=5_000_000,
        max_api_keys=10,
        rate_limit_per_min=120,
    ),
    "team": PlanLimits(
        requests_per_day=20_000,
        tokens_per_month=20_000_000,
        max_api_keys=50,
        rate_limit_per_min=300,
    ),
    "studio": PlanLimits(
        requests_per_day=UNLIMITED,
        tokens_per_month=UNLIMITED,
        max_api_keys=UNLIMITED,
        rate_limit_per_min=UNLIMITED,
    ),
    "enterprise": PlanLimits(
        requests_per_day=UNLIMITED,
        tokens_per_month=UNLIMITED,
        max_api_keys=UNLIMITED,
        rate_limit_per_min=UNLIMITED,
    ),
}

# Fail-fast (P2/P3): політика мусить покривати рівно `VALID_PLANS` — інакше план без
# стель «протече» повз enforcement. Звіряємо на імпорті, поки SSOT один.
assert set(PLAN_LIMITS) == set(VALID_PLANS), (
    "PLAN_LIMITS must cover exactly VALID_PLANS "
    f"(missing={set(VALID_PLANS) - set(PLAN_LIMITS)}, extra={set(PLAN_LIMITS) - set(VALID_PLANS)})"
)


def limits_for(plan: str) -> PlanLimits:
    """Ліміти плану. Невідомий план → `free` (найсуворіші, fail-closed для білінгу)."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def exceeds(plan: str, resource: str, current: int) -> bool:
    """Чи досяг `current` стелі `resource` для `plan` (→ `402`). Невідомий ресурс → `ValueError`."""
    return limits_for(plan).exceeds(resource, current)


def public_limits(plan: str) -> dict[str, int | None]:
    """Публічна проєкція стель плану для API/консолі (`/whoami`, Billing-таб AP-6.4).

    `UNLIMITED` (`-1`) → `None` — чесний JSON «без стелі», щоб клієнт не трактував
    службове `-1` як реальний ліміт. Решта — як є (включно з `0` = повна заборона).
    """
    lim = limits_for(plan)
    return {r: (None if lim.cap(r) == UNLIMITED else lim.cap(r)) for r in RESOURCES}


# ── AP-4.5: soft/hard ліміти + grace ───────────────────────────────────────────
# `exceeds` дає одну (жорстку) межу на стелі. AP-4.5 розрізняє «soft» (стеля плану) і
# «hard» (стеля + grace-смуга) та політику «fail-open ops, fail-closed billing»:
#
#   * **ops** (`requests_per_day`, `rate_limit_per_min`) — операційні лічильники. Транзієнтний
#     сплеск не має одразу різати доступ: над стелею є grace-смуга, де дія ще проходить, але
#     позначається `GRACE` (попередити/білити overage). Якщо лічильник недоступний (Redis-збій) —
#     **fail-open** (дозволити): операційний guard не повинен класти запит через інфра-збій.
#   * **billing** (`tokens_per_month`, `max_api_keys`) — тарифні/провіженінг-стелі. Grace немає:
#     `hard == soft`, на стелі вже `BLOCKED`. За невизначеності лічильника — **fail-closed**
#     (відхилити): не роздаємо неоплачений ресурс.
#
# Чисто (дані + детерміновані переходи), без Redis/HTTP — request-path enforcement підключає це
# окремо так само, як робить із `exceeds` (див. модульний docstring). UNLIMITED → завжди `OK`.

# Дефолтна grace-смуга над soft-стелею для ops-ресурсів (10%). Перекривається аргументом.
DEFAULT_GRACE = 0.10

# Класифікація ресурсу: чи операційний (fail-open + grace) чи тарифний/провіженінг (fail-closed).
RESOURCE_KIND: dict[str, str] = {
    "requests_per_day": "ops",
    "rate_limit_per_min": "ops",
    "tokens_per_month": "billing",
    "max_api_keys": "billing",
}

# Fail-fast (P2/P3): kind-мапа мусить покривати рівно `RESOURCES`, інакше ресурс «протече» повз
# політику grace/fail-open. Звіряємо на імпорті — той самий патерн, що `PLAN_LIMITS == VALID_PLANS`.
assert set(RESOURCE_KIND) == set(RESOURCES), (
    "RESOURCE_KIND must cover exactly RESOURCES "
    f"(missing={set(RESOURCES) - set(RESOURCE_KIND)}, extra={set(RESOURCE_KIND) - set(RESOURCES)})"
)


class LimitStatus(str, Enum):
    """Стан ресурсу відносно стелі плану. `str`-enum — серіалізується як рядок у JSON/лог."""

    OK = "ok"          # під soft-стелею — дозволити без позначки
    GRACE = "grace"    # у grace-смузі [soft, hard) для ops — дозволити, але позначити overage
    BLOCKED = "blocked"  # на/над hard (ops) або на/над soft (billing) — відхилити (`402`)


def is_ops(resource: str) -> bool:
    """Чи ресурс операційний (ops). Невідомий ресурс → `ValueError` (fail-fast, як `cap`)."""
    if resource not in RESOURCE_KIND:
        raise ValueError(f"unknown resource: {resource!r}")
    return RESOURCE_KIND[resource] == "ops"


def fail_open(resource: str) -> bool:
    """Політика за недоступного лічильника: ops → `True` (fail-open), billing → `False`.

    Контракт для request-path enforcement (AP-4.5): коли usage недоступний (Redis-збій),
    операційний guard пропускає (`fail-open ops`), а білінговий відхиляє (`fail-closed billing`).
    """
    return is_ops(resource)


def hard_cap(plan: str, resource: str, grace: float = DEFAULT_GRACE) -> int:
    """Hard-стеля: ops отримує grace-смугу над soft-стелею; billing — без grace (`hard == soft`).

    `UNLIMITED` → `UNLIMITED`. Невідомий ресурс → `ValueError`. Grace застосовується через
    `floor(cap·(1+grace))`, тож стеля `0` (повна заборона) лишається `0` за будь-якого grace.
    """
    cap = limits_for(plan).cap(resource)
    if cap == UNLIMITED:
        return UNLIMITED
    if is_ops(resource) and grace > 0:
        return int(cap * (1.0 + grace))  # floor для додатних — grace ніколи не «округляє вгору» 0
    return cap


def classify(plan: str, resource: str, current: int, grace: float = DEFAULT_GRACE) -> LimitStatus:
    """Класифікує `current` як `OK`/`GRACE`/`BLOCKED` для `plan`/`resource` (AP-4.5).

    * `UNLIMITED` → завжди `OK` (S2: self-hosted `studio` ніколи не впирається).
    * `current < soft` → `OK`.
    * billing → на/над soft одразу `BLOCKED` (grace немає, fail-closed).
    * ops → `[soft, hard)` → `GRACE`; на/над `hard` → `BLOCKED`.
    Невідомий ресурс → `ValueError`. Узгоджено з `exceeds` (soft-межа = `current >= soft`).
    """
    soft = limits_for(plan).cap(resource)
    if soft == UNLIMITED:
        return LimitStatus.OK
    if current < soft:
        return LimitStatus.OK
    if not is_ops(resource):
        return LimitStatus.BLOCKED
    return LimitStatus.GRACE if current < hard_cap(plan, resource, grace) else LimitStatus.BLOCKED
