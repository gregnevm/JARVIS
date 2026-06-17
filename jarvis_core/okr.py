"""OKR/goals модель для авто-корутини (autopilot / Stowp E).

Чисті дата-класи + (де)серіалізація + чисті функції **вибору цілі** і **мутації
прогресу за адмін-контекстом**. Жодних залежностей від сервісів чи IO — тож
ганяється в `jarvis_core/tests` і переюзається gateway-корутиною.

Модель:
- `KeyResult` — вимірюваний результат (progress 0..target).
- `Objective` — ціль із пріоритетом, roadmap-джерелом задач і набором KR.
- `OKR` — кореневий контейнер: список цілей + вільний `admin_context` (фокус/
  обмеження адміна, яким керується мутація) + лічильник циклів.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

SCHEMA_VERSION = 1
_EPS = 1e-9


@dataclass(frozen=True)
class KeyResult:
    """Вимірюваний результат цілі. `progress`/`target` у тих самих одиницях."""

    id: str
    text: str
    target: float = 1.0
    progress: float = 0.0
    metric: str = "ratio"  # ratio | count | tests | bool

    @property
    def done(self) -> bool:
        return self.progress >= self.target - _EPS

    @property
    def ratio(self) -> float:
        """Нормований прогрес 0..1 (з кліпом)."""
        if self.target <= 0:
            return 1.0
        return max(0.0, min(self.progress / self.target, 1.0))


@dataclass(frozen=True)
class Objective:
    """Ціль autopilot. `roadmap` — шлях до доку, з якого беруться задачі."""

    id: str
    title: str
    roadmap: str = ""
    priority: int = 3  # 1 (найвищий) .. 5 (найнижчий)
    status: str = "active"  # active | paused | done
    key_results: tuple[KeyResult, ...] = ()

    @property
    def progress(self) -> float:
        if not self.key_results:
            return 0.0
        return sum(kr.ratio for kr in self.key_results) / len(self.key_results)

    @property
    def is_met(self) -> bool:
        return bool(self.key_results) and all(kr.done for kr in self.key_results)


@dataclass(frozen=True)
class OKR:
    """Кореневий OKR-контейнер."""

    objectives: tuple[Objective, ...] = ()
    admin_context: str = ""
    cycle: int = 0
    schema_version: int = SCHEMA_VERSION

    @property
    def progress(self) -> float:
        active = [o for o in self.objectives if o.status != "paused"]
        if not active:
            return 0.0
        return sum(o.progress for o in active) / len(active)


# --- вибір цілі (чиста логіка) -------------------------------------------------

def select_objective(okr: OKR) -> Objective | None:
    """Наступна ціль для прогону: active, ще не досягнута.

    Сортування: пріоритет ↑ (1 — найважливіше), далі найменш просунута,
    далі за `id` (детермінізм). `None` — якщо робити нічого.
    """
    candidates = [
        o for o in okr.objectives if o.status == "active" and not o.is_met
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda o: (o.priority, o.progress, o.id))


# --- мутація OKR (чиста логіка) ------------------------------------------------

def _clamp_progress(kr: KeyResult, delta: float) -> KeyResult:
    new = max(0.0, min(kr.progress + delta, kr.target))
    return replace(kr, progress=new)


def _apply_kr_deltas(
    objectives: tuple[Objective, ...], kr_deltas: dict[str, float]
) -> tuple[Objective, ...]:
    if not kr_deltas:
        return objectives
    out: list[Objective] = []
    for obj in objectives:
        krs = tuple(
            _clamp_progress(kr, kr_deltas[kr.id]) if kr.id in kr_deltas else kr
            for kr in obj.key_results
        )
        status = "done" if (krs and all(k.done for k in krs)) else obj.status
        out.append(replace(obj, key_results=krs, status=status))
    return tuple(out)


def _apply_admin_priorities(
    objectives: tuple[Objective, ...], admin_context: str
) -> tuple[Objective, ...]:
    """Адмін-контекст піднімає пріоритет цілей, чий `id`/`title` згаданий.

    Детерміновано: збіг (case-insensitive substring) → priority = max(1, p-1).
    Так адмін «однією фразою» перенацілює корутину без ручного редагування JSON.
    """
    ctx = (admin_context or "").lower()
    if not ctx.strip():
        return objectives
    out: list[Objective] = []
    for obj in objectives:
        hit = obj.id.lower() in ctx or (obj.title.lower() in ctx if obj.title else False)
        if hit and obj.status == "active":
            out.append(replace(obj, priority=max(1, obj.priority - 1)))
        else:
            out.append(obj)
    return tuple(out)


def mutate_okr(
    okr: OKR,
    *,
    admin_context: str | None = None,
    kr_deltas: dict[str, float] | None = None,
) -> OKR:
    """Породжує новий OKR після циклу autopilot.

    1) `admin_context` (якщо переданий) перезаписує наявний;
    2) `kr_deltas` (kr_id → дельта прогресу) застосовуються з кліпом;
    3) цілі з усіма досягнутими KR → `status="done"`;
    4) адмін-контекст піднімає пріоритети релевантних цілей;
    5) `cycle += 1`.
    """
    ctx = okr.admin_context if admin_context is None else admin_context
    objectives = _apply_kr_deltas(okr.objectives, kr_deltas or {})
    objectives = _apply_admin_priorities(objectives, ctx)
    return replace(okr, objectives=objectives, admin_context=ctx, cycle=okr.cycle + 1)


# --- (де)серіалізація ----------------------------------------------------------

def kr_from_dict(d: dict[str, Any]) -> KeyResult:
    return KeyResult(
        id=str(d["id"]),
        text=str(d.get("text", "")),
        target=float(d.get("target", 1.0)),
        progress=float(d.get("progress", 0.0)),
        metric=str(d.get("metric", "ratio")),
    )


def objective_from_dict(d: dict[str, Any]) -> Objective:
    return Objective(
        id=str(d["id"]),
        title=str(d.get("title", "")),
        roadmap=str(d.get("roadmap", "")),
        priority=int(d.get("priority", 3)),
        status=str(d.get("status", "active")),
        key_results=tuple(kr_from_dict(k) for k in d.get("key_results", [])),
    )


def okr_from_dict(d: dict[str, Any]) -> OKR:
    return OKR(
        objectives=tuple(objective_from_dict(o) for o in d.get("objectives", [])),
        admin_context=str(d.get("admin_context", "")),
        cycle=int(d.get("cycle", 0)),
        schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
    )


def kr_to_dict(kr: KeyResult) -> dict[str, Any]:
    return {
        "id": kr.id,
        "text": kr.text,
        "target": kr.target,
        "progress": kr.progress,
        "metric": kr.metric,
    }


def objective_to_dict(obj: Objective) -> dict[str, Any]:
    return {
        "id": obj.id,
        "title": obj.title,
        "roadmap": obj.roadmap,
        "priority": obj.priority,
        "status": obj.status,
        "progress": round(obj.progress, 4),
        "key_results": [kr_to_dict(kr) for kr in obj.key_results],
    }


def okr_to_dict(okr: OKR) -> dict[str, Any]:
    return {
        "schema_version": okr.schema_version,
        "cycle": okr.cycle,
        "admin_context": okr.admin_context,
        "progress": round(okr.progress, 4),
        "objectives": [objective_to_dict(o) for o in okr.objectives],
    }
