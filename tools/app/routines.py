"""Рутини (SY-9 «пропозиція → рутина»): S4-апрув → рядок Windows Task Scheduler.

Патерн — благословенний ADR-008 спосіб рекурентності: scheduled task на ХОСТІ
б'є `scripts/jarvis_context.py --job <job>` → gateway `/api/v1/context/jobs/*`
(рекурентність із нагляду користувача, не прихований auto-cron). Матеріалізація
йде через host-agent `/cli` (`schtasks` — не Get-ScheduledTask: той висне в
дочірньому PS) тим самим шляхом, що autopilot-apply.

S4: створення/вимкнення рутини = явний user-initiated API-виклик (апрув і є
викликом). Кожна зміна стану — паспорт `kind:routine`; кожен запуск джоба —
`kind:routine_run` (аудит рутин ретривом, DoD SY-9). Прапор `ENABLE_ROUTINES`.
"""
from __future__ import annotations

import re
from typing import Any

from .computer import hostagent_cli
from .config import settings
from .context_emit import emit_context_event

ROUTINE_TASK_PREFIX = "JARVIS_routine_"

# SY-9.1: мапа «пропозиція → job» (LLM-free проєкція). Ключ = context-job,
# script_job = аргумент --job у jarvis_context.py, keywords — матчинг тексту пропозиції.
ROUTINE_JOBS: dict[str, dict[str, Any]] = {
    "context_daily": {
        "script_job": "daily",
        "keywords": ("дайджест", "daily", "щоден", "підсумок дня"),
    },
    "context_summarize": {
        "script_job": "summarize",
        "keywords": ("сумариз", "summar", "дозведи", "pending"),
    },
    "context_retention": {
        "script_job": "retention",
        "keywords": ("retention", "чистк", "ретенш", "видаляй стар"),
    },
}


def project_proposal(text: str) -> str | None:
    """SY-9.1: проєкція тексту пропозиції на job. None = не мапиться (не рутинна)."""
    t = (text or "").lower()
    for job, spec in ROUTINE_JOBS.items():
        if any(k in t for k in spec["keywords"]):
            return job
    return None


def _task_name(job: str) -> str:
    return f"{ROUTINE_TASK_PREFIX}{job}"


def _task_command(job: str) -> str:
    """Командний рядок task-а: python-скрипт колектора з --job (ADR-008 патерн).

    Auth скрипт бере з env хоста (JARVIS_PASSWORD/JARVIS_TOKEN) — секрети не
    потрапляють у визначення task-а.
    """
    repo = settings.routines_host_repo.rstrip("/\\")
    script = repo + "\\scripts\\jarvis_context.py"
    url = settings.routines_gateway_url.strip() or "http://127.0.0.1:8000"
    script_job = str(ROUTINE_JOBS[job]["script_job"])
    return f'{settings.routines_python_exe} "{script}" --job {script_job} --url {url}'


def _guard() -> str | None:
    if not settings.enable_routines:
        return "Рутини вимкнено (ENABLE_ROUTINES=false)."
    if not settings.routines_host_repo.strip():
        return "ROUTINES_HOST_REPO порожній — вкажи шлях до репо на хості (напр. O:\\JARVIS)."
    return None


def _emit_routine_state(user_id: int, job: str, status: str, *, proposal_ref: str = "") -> None:
    emit_context_event(
        {
            "user_id": user_id,
            "kind": "routine",
            "summary": f"Рутина {job}: {status}",
            "tags": [f"routine:{job}", f"status:{status}", "module:routines"],
            "source": "routines",
            "sensitivity": "personal",
            "ref": proposal_ref or None,
            "payload": {"job": job, "task": _task_name(job)},
        }
    )


def emit_routine_run(user_id: int, job: str, result: dict[str, Any]) -> None:
    """SY-9.3: кожен запуск context-job — run-паспорт (аудит рутин ретривом)."""
    if not settings.enable_routines:
        return
    brief = ", ".join(f"{k}={v}" for k, v in result.items() if k != "job")
    emit_context_event(
        {
            "user_id": user_id,
            "kind": "routine_run",
            "summary": f"Запуск {job}: {brief}"[:300],
            "tags": [f"routine:{job}", "module:routines"],
            "source": "routines",
            "sensitivity": "personal",
            "payload": {"job": job, "result": result},
        }
    )


async def create_routine(
    user_id: int, job: str, *, hour: int, minute: int = 0, proposal_ref: str = ""
) -> dict[str, Any]:
    """SY-9.2: матеріалізація — апрув (сам виклик) → schtasks /Create (щоденно HH:MM)."""
    err = _guard()
    if err:
        return {"error": err}
    if job not in ROUTINE_JOBS:
        return {"error": f"невідома рутина: {job} (доступні: {', '.join(ROUTINE_JOBS)})"}
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return {"error": "hour 0-23, minute 0-59"}
    st = f"{hour:02d}:{minute:02d}"
    out = await hostagent_cli(
        "schtasks",
        [
            "/Create", "/TN", _task_name(job), "/TR", _task_command(job),
            "/SC", "DAILY", "/ST", st, "/F",
        ],
    )
    if out.get("error") or int(out.get("code", -1)) != 0:
        detail = str(out.get("error") or out.get("stderr") or "")[:200]
        return {"error": f"schtasks create failed: {detail}"}
    _emit_routine_state(user_id, job, "active", proposal_ref=proposal_ref)
    return {"job": job, "task": _task_name(job), "schedule": f"DAILY {st}", "status": "active"}


async def disable_routine(user_id: int, job: str) -> dict[str, Any]:
    """Вимкнути одним кліком (SY-9.4): schtasks /Delete (повне зняття рядка)."""
    err = _guard()
    if err:
        return {"error": err}
    if job not in ROUTINE_JOBS:
        return {"error": f"невідома рутина: {job}"}
    out = await hostagent_cli("schtasks", ["/Delete", "/TN", _task_name(job), "/F"])
    if out.get("error") or int(out.get("code", -1)) != 0:
        detail = str(out.get("error") or out.get("stderr") or "")[:200]
        return {"error": f"schtasks delete failed: {detail}"}
    _emit_routine_state(user_id, job, "disabled")
    return {"job": job, "task": _task_name(job), "status": "disabled"}


def _parse_schtasks_csv(stdout: str) -> list[dict[str, str]]:
    """CSV-вивід `schtasks /Query /FO CSV` → рядки наших task-ів (без csv-модуля
    не обійтись — коми в лапках), фільтр за префіксом."""
    import csv
    import io

    rows: list[dict[str, str]] = []
    reader = csv.reader(io.StringIO(stdout))
    for cells in reader:
        if len(cells) < 3 or cells[0].startswith("TaskName") or cells[0] == "":
            continue
        name = cells[0].strip().lstrip("\\")
        if not name.startswith(ROUTINE_TASK_PREFIX):
            continue
        rows.append({
            "task": name,
            "job": name.removeprefix(ROUTINE_TASK_PREFIX),
            "next_run": cells[1].strip(),
            "status": cells[2].strip(),
        })
    return rows


async def list_routines() -> dict[str, Any]:
    """Список активних рутин — джерело правди сам Task Scheduler (schtasks /Query)."""
    err = _guard()
    if err:
        return {"error": err, "routines": []}
    out = await hostagent_cli("schtasks", ["/Query", "/FO", "CSV", "/NH"])
    if out.get("error"):
        return {"error": str(out["error"])[:200], "routines": []}
    return {"routines": _parse_schtasks_csv(str(out.get("stdout", ""))),
            "available": sorted(ROUTINE_JOBS)}


_HOUR_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def parse_schedule_hint(text: str) -> tuple[int, int]:
    """Час із тексту пропозиції («о 8:30») → (hour, minute); дефолт 08:00."""
    m = _HOUR_RE.search(text or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return 8, 0
