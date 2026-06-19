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
