"""Auto-code coroutine — автономний OKR-керований цикл розробки (default off).

Замикає 6-фазний цикл **без підтвердження**, керуючись OKR/goals + адмін-контекстом:

  1. `code`     — пише код під вибрану ціль за її roadmap (orchestrator/coding job);
  2. `review`   — self-improve scan + code review знайденого діфа;
  3. `refactor` — рефактор за зауваженнями review;
  4. `analyze`  — cleanup + аналіз архітектури (репо-дерево, артефакт);
  5. `test`     — run & fix tests (headless coding job → `/agent/code/fix`);
  6. `evolve`   — мутує OKR (прогрес KR + пере-пріоритезація за адмін-контекстом).

Архітектура (як `context_scheduler`): **чистий планувальник** (`plan_cycle`) +
**чистий рендер** (`render_dashboard`) тестуються ізольовано; IO-цикл
(`auto_coroutine_loop`) тонкий і default-off (ADR-008 — запуск під наглядом).
Фактичне виконання фаз інжектиться як `StageDispatch`, тож у тестах підставляється
фейк, а в проді — `make_tools_dispatch` (через наявний `ToolsClient`). Мутуючі
фази додатково гейтяться tools-політикою `CODING_HEADLESS_APPLY`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis_core.okr import OKR, Objective, mutate_okr, okr_from_dict, okr_to_dict, select_objective

logger = logging.getLogger("jarvis.gateway.auto_coroutine")

# Порядок фаз циклу (id → людська назва для логів/дашборда).
STAGES: tuple[tuple[str, str], ...] = (
    ("code", "Код за roadmap"),
    ("review", "Review"),
    ("refactor", "Refactor"),
    ("analyze", "Cleanup + архітектура"),
    ("test", "Run & test"),
    ("evolve", "Еволюція roadmap (OKR)"),
)
STAGE_IDS: tuple[str, ...] = tuple(s for s, _ in STAGES)


@dataclass(frozen=True)
class StageContext:
    """Вхід однієї фази: ціль, фаза, репо й накопичені нотатки попередніх фаз."""

    objective: Objective
    stage: str
    user_id: int
    repo_path: str
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StageOutcome:
    """Результат фази. `kr_progress` — дельти прогресу KR (kr_id → +ratio)."""

    ok: bool
    summary: str
    artifact: str = ""
    kr_progress: dict[str, float] = field(default_factory=dict)


# Інжектована точка виконання фаз. Прод: `make_tools_dispatch`; тест: фейк.
StageDispatch = Callable[[StageContext], Awaitable[StageOutcome]]


@dataclass(frozen=True)
class CycleResult:
    """Підсумок одного циклу для run-log і дашборда."""

    objective_id: str
    objective_title: str
    started_at: str
    stages: list[tuple[str, bool, str]]  # (stage_id, ok, summary)
    advanced: bool

    @property
    def ok_count(self) -> int:
        return sum(1 for _, ok, _ in self.stages if ok)


# --- чистий планувальник -------------------------------------------------------

def plan_cycle(okr: OKR) -> Objective | None:
    """Яку ціль крутимо цього циклу (`None` → нічого; корутина спить)."""
    return select_objective(okr)


def outcome_deltas(objective: Objective, outcomes: list[StageOutcome]) -> dict[str, float]:
    """Зводить дельти KR із усіх фаз циклу.

    Явні `kr_progress` з фаз застосовуються як є. Додатково: успішні фази без
    явних дельт «штовхають» найменш просунутий ще-не-готовий KR цілі (детерміновано),
    щоб прогрес був видимим навіть для загальних фаз (review/analyze).
    """
    deltas: dict[str, float] = {}
    for oc in outcomes:
        for kr_id, d in oc.kr_progress.items():
            deltas[kr_id] = deltas.get(kr_id, 0.0) + d

    open_krs = [kr for kr in objective.key_results if not kr.done]
    if open_krs:
        target = min(open_krs, key=lambda k: (k.ratio, k.id))
        implicit = sum(0.05 for oc in outcomes if oc.ok and not oc.kr_progress)
        if implicit:
            deltas[target.id] = deltas.get(target.id, 0.0) + implicit
    return deltas


# --- цикл (async, IO через інжектований dispatch) ------------------------------

async def run_cycle(
    okr: OKR,
    dispatch: StageDispatch,
    *,
    user_id: int,
    repo_path: str,
    now: datetime | None = None,
) -> tuple[OKR, CycleResult | None]:
    """Один повний 6-фазний цикл по вибраній цілі.

    Повертає (новий OKR, CycleResult|None). `None` — коли активних цілей немає.
    Фаза `evolve` не диспатчиться: це і є мутація OKR тут-таки.
    """
    objective = plan_cycle(okr)
    if objective is None:
        return okr, None

    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    outcomes: list[StageOutcome] = []
    notes: dict[str, str] = {}
    rows: list[tuple[str, bool, str]] = []

    for stage_id, _label in STAGES:
        if stage_id == "evolve":
            break
        ctx = StageContext(
            objective=objective,
            stage=stage_id,
            user_id=user_id,
            repo_path=repo_path,
            notes=dict(notes),
        )
        try:
            outcome = await dispatch(ctx)
        except Exception as exc:  # noqa: BLE001 — одна фаза не валить цикл
            logger.warning("stage %s failed: %s", stage_id, type(exc).__name__)
            outcome = StageOutcome(ok=False, summary=f"error: {type(exc).__name__}")
        outcomes.append(outcome)
        notes[stage_id] = outcome.summary
        rows.append((stage_id, outcome.ok, outcome.summary))

    deltas = outcome_deltas(objective, outcomes)
    new_okr = mutate_okr(okr, kr_deltas=deltas)
    advanced = bool(deltas)
    rows.append(("evolve", advanced, f"KR Δ: {len(deltas)} · cycle={new_okr.cycle}"))

    result = CycleResult(
        objective_id=objective.id,
        objective_title=objective.title,
        started_at=ts,
        stages=rows,
        advanced=advanced,
    )
    return new_okr, result


# --- сховище OKR + run-log (тонкий IO) -----------------------------------------

def _okr_path(data_dir: str) -> Path:
    return Path(data_dir) / "okr" / "okr.json"


def load_okr(data_dir: str) -> OKR:
    """Читає OKR із `<data_dir>/okr/okr.json`. Відсутній/битий → порожній OKR."""
    path = _okr_path(data_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return OKR()
    return okr_from_dict(raw if isinstance(raw, dict) else {})


def save_okr(data_dir: str, okr: OKR) -> None:
    path = _okr_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(okr_to_dict(okr), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def append_run_log(data_dir: str, result: CycleResult) -> None:
    """Дописує підсумок циклу у `<data_dir>/autopilot/run_log.md` (append-only)."""
    path = Path(data_dir) / "autopilot" / "run_log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"\n## Cycle @ {result.started_at} — {result.objective_id} "
        f"({result.ok_count}/{len(result.stages)} ok)",
        f"> {result.objective_title}",
        "",
    ]
    for stage_id, ok, summary in result.stages:
        lines.append(f"- {'✅' if ok else '⚠️'} **{stage_id}** — {summary}")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --- дашборд (чистий рендер) ---------------------------------------------------

def render_dashboard(okr: OKR, recent: list[CycleResult]) -> str:
    """Markdown-дашборд OKR-прогресу + останні цикли (для artifact-канвасу)."""
    bar_w = 20

    def bar(ratio: float) -> str:
        filled = int(round(max(0.0, min(ratio, 1.0)) * bar_w))
        return "█" * filled + "░" * (bar_w - filled)

    out: list[str] = [
        "# 🤖 Autopilot — OKR Dashboard",
        "",
        f"**Цикл:** {okr.cycle} · **Загальний прогрес:** {okr.progress * 100:.0f}%",
    ]
    if okr.admin_context.strip():
        out += ["", f"> 🧭 **Admin context:** {okr.admin_context.strip()}"]
    out += ["", "## Objectives", ""]
    for obj in sorted(okr.objectives, key=lambda o: (o.priority, o.id)):
        flag = {"done": "🏁", "paused": "⏸️", "active": "▶️"}.get(obj.status, "•")
        out.append(
            f"### {flag} `{obj.id}` P{obj.priority} — {obj.title} "
            f"`{bar(obj.progress)}` {obj.progress * 100:.0f}%"
        )
        for kr in obj.key_results:
            mark = "✅" if kr.done else "⬜"
            out.append(f"- {mark} {kr.text} `{bar(kr.ratio)}` {kr.ratio * 100:.0f}%")
        out.append("")
    if recent:
        out += ["## Recent cycles", ""]
        for r in recent[-5:][::-1]:
            out.append(
                f"- `{r.started_at}` **{r.objective_id}** "
                f"— {r.ok_count}/{len(r.stages)} ok{' · 📈' if r.advanced else ''}"
            )
    return "\n".join(out).rstrip() + "\n"


def save_dashboard(data_dir: str, okr: OKR, recent: list[CycleResult]) -> Path:
    path = Path(data_dir) / "autopilot" / "dashboard.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(okr, recent), encoding="utf-8")
    return path


# --- прод-диспатч (через ToolsClient) ------------------------------------------

def _err(out: dict[str, Any]) -> str | None:
    e = out.get("error")
    return str(e) if e else None


def make_tools_dispatch(tools: Any, *, worker_budget: int = 4) -> StageDispatch:
    """Прод-диспатч: маршрутизує фази на наявні tools-RPC.

    `code`/`refactor`/`analyze` → orchestrator (планує+кодить); `review` →
    self-improve scan; `test` → headless coding job (`/agent/code/fix`, pytest).
    Усі мутації — `no_confirm`, гейтяться `CODING_HEADLESS_APPLY` на tools-боці.
    """

    async def _orchestrate(task: str, ctx: StageContext) -> StageOutcome:
        out = await tools.spawn_orchestrator(ctx.user_id, task, worker_budget=worker_budget)
        err = _err(out)
        return StageOutcome(
            ok=err is None,
            summary=err or f"orchestrator run {out.get('run_id') or out.get('job_id') or 'spawned'}",
        )

    async def dispatch(ctx: StageContext) -> StageOutcome:
        obj = ctx.objective
        src = obj.roadmap or "ROADMAP.md"
        if ctx.stage == "code":
            return await _orchestrate(
                f"Реалізуй наступний actionable-пункт із {src} для цілі «{obj.title}» "
                f"({obj.id}). Малий вертикальний зріз + тести. Не чіпай секрети/інфру.",
                ctx,
            )
        if ctx.stage == "review":
            out = await tools.improve_scan(ctx.user_id)
            err = _err(out)
            n = len(out.get("items") or out.get("pending") or [])
            return StageOutcome(ok=err is None, summary=err or f"scan: {n} пропозицій")
        if ctx.stage == "refactor":
            return await _orchestrate(
                f"Рефактор за зауваженнями review для «{obj.title}»: "
                f"{ctx.notes.get('review', 'cleanup')}. Без зміни поведінки; тести зелені.",
                ctx,
            )
        if ctx.stage == "analyze":
            out = await tools.repo_tree(ctx.user_id) if hasattr(tools, "repo_tree") else {}
            err = _err(out) if isinstance(out, dict) else None
            return StageOutcome(
                ok=err is None,
                summary=err or "архітектурний знімок репо знято",
                artifact=str(out.get("tree", "")) if isinstance(out, dict) else "",
            )
        if ctx.stage == "test":
            out = await tools.create_coding_job(
                ctx.user_id, "pytest", path=ctx.repo_path, task=f"green tests for {obj.id}"
            )
            err = _err(out)
            return StageOutcome(
                ok=err is None,
                summary=err or f"test job {out.get('job_id') or out.get('id') or 'queued'}",
                kr_progress={},
            )
        return StageOutcome(ok=True, summary="noop")

    return dispatch


# --- локальний диспатч (без зовн. сервісів — для наглядового прогону) -----------

async def _run_cmd(cmd: list[str], cwd: str, timeout: float = 600.0) -> tuple[int, str]:
    """Запускає підпроцес, повертає (returncode, об'єднаний stdout+stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        raw, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "timeout"
    return proc.returncode or 0, raw.decode("utf-8", errors="replace")


def _repo_snapshot(repo_path: str) -> tuple[int, int, str]:
    """Грубий знімок архітектури: (py-файлів, тек-модулів, top-level дерево)."""
    root = Path(repo_path)
    skip = {".git", ".venv", "__pycache__", "node_modules", ".jarvis_backup"}
    py = 0
    dirs = 0
    for p in root.rglob("*"):
        if any(part in skip for part in p.parts):
            continue
        if p.is_dir():
            dirs += 1
        elif p.suffix == ".py":
            py += 1
    top = sorted(
        d.name for d in root.iterdir() if d.is_dir() and d.name not in skip
    )
    return py, dirs, ", ".join(top)


def _pytest_summary(out: str, code: int) -> str:
    """Витягує `N passed/failed/error…` із виводу pytest; інакше — за exit-кодом."""
    import re

    m = re.search(r"=+ ([^=]*\b(?:passed|failed|error|skipped)[^=]*?) =+\s*$", out.strip())
    if m:
        return m.group(1).strip()
    counts = re.findall(r"\b(\d+) (passed|failed|error|errors|skipped)\b", out)
    if counts:
        return ", ".join(f"{n} {label}" for n, label in counts)
    return "усі зелені" if code == 0 else f"впав (exit {code})"


def make_local_dispatch(
    repo_path: str, *, test_targets: list[str] | None = None
) -> StageDispatch:
    """Диспатч без зовнішніх сервісів: `test` — справжній pytest, `analyze` — знімок
    репо, `review` — `git diff --stat`. `code`/`refactor` — зафіксований план (без
    codegen, бо тут немає LLM/agent). Для наглядового першого прогону й офлайн-демо.
    """
    targets = test_targets or ["jarvis_core/tests/test_okr.py"]

    async def dispatch(ctx: StageContext) -> StageOutcome:
        obj = ctx.objective
        if ctx.stage in ("code", "refactor"):
            src = obj.roadmap or "ROADMAP.md"
            return StageOutcome(
                ok=True,
                summary=f"план зафіксовано (local mode, без codegen): {ctx.stage} «{obj.title}» ← {src}",
            )
        if ctx.stage == "review":
            code, out = await _run_cmd(["git", "diff", "--stat", "HEAD~1"], repo_path, timeout=60)
            last = out.strip().splitlines()[-1] if out.strip() else "без змін"
            return StageOutcome(ok=code == 0, summary=f"git diff: {last}")
        if ctx.stage == "analyze":
            py, dirs, top = _repo_snapshot(repo_path)
            return StageOutcome(
                ok=True,
                summary=f"архітектура: {py} py-файлів, {dirs} тек",
                artifact=f"top-level: {top}",
            )
        if ctx.stage == "test":
            code, out = await _run_cmd(["python", "-m", "pytest", "-ra", *targets], repo_path)
            return StageOutcome(ok=code == 0, summary=f"pytest: {_pytest_summary(out, code)}")
        return StageOutcome(ok=True, summary="noop")

    return dispatch


# --- IO-цикл (default off) -----------------------------------------------------

async def auto_coroutine_loop(
    *,
    data_dir: str,
    user_id: int,
    repo_path: str,
    dispatch: StageDispatch,
    interval: float,
) -> None:
    """Періодично крутить `run_cycle`, зберігає OKR, run-log і дашборд."""
    logger.info("Auto-coroutine started (interval=%ss user=%s)", interval, user_id)
    recent: list[CycleResult] = []
    while True:
        try:
            okr = load_okr(data_dir)
            new_okr, result = await run_cycle(
                okr, dispatch, user_id=user_id, repo_path=repo_path
            )
            if result is not None:
                save_okr(data_dir, new_okr)
                append_run_log(data_dir, result)
                recent.append(result)
                save_dashboard(data_dir, new_okr, recent)
                logger.info(
                    "cycle done: %s (%d/%d ok)",
                    result.objective_id,
                    result.ok_count,
                    len(result.stages),
                )
            else:
                logger.info("auto-coroutine idle: no actionable objectives")
        except asyncio.CancelledError:
            logger.info("Auto-coroutine stopped")
            raise
        except Exception as exc:  # noqa: BLE001 — тік не валить процес
            logger.warning("auto-coroutine tick failed: %s", exc)
        await asyncio.sleep(interval)
