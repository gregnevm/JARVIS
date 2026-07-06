"""SY-9: пропозиція → рутина — проєкція, матеріалізація schtasks, паспорти, список."""
from __future__ import annotations

from typing import Any

import pytest
from app import context_emit, routines
from app.config import settings


class _IngestSpy:
    def __init__(self) -> None:
        self.stores: list[dict[str, Any]] = []

    async def context_ingest(self, store: dict[str, Any]) -> dict[str, Any]:
        self.stores.append(store)
        return {"inserted": True}


class _CliSpy:
    def __init__(self, out: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.out = out or {"stdout": "", "stderr": "", "code": 0}

    async def __call__(self, exe: str, args: list[str]) -> dict[str, Any]:
        self.calls.append((exe, args))
        return dict(self.out)


@pytest.fixture
def env(monkeypatch):
    ingest = _IngestSpy()
    cli = _CliSpy()
    monkeypatch.setattr(context_emit, "_memory", ingest)
    monkeypatch.setattr(routines, "hostagent_cli", cli)
    monkeypatch.setattr(settings, "enable_routines", True)
    monkeypatch.setattr(settings, "routines_host_repo", "O:\\JARVIS")
    monkeypatch.setattr(settings, "routines_python_exe", "python")
    monkeypatch.setattr(settings, "routines_gateway_url", "http://127.0.0.1:8000")
    return ingest, cli


# --- SY-9.1: проєкція пропозиції ---

def test_project_proposal_mapping():
    assert routines.project_proposal("Робити щоденний дайджест зранку") == "context_daily"
    assert routines.project_proposal("дозведи pending нотатки") == "context_summarize"
    assert routines.project_proposal("чистка старих подій (retention)") == "context_retention"
    assert routines.project_proposal("подзвонити мамі") is None


def test_parse_schedule_hint():
    assert routines.parse_schedule_hint("щодня о 8:30 ранку") == (8, 30)
    assert routines.parse_schedule_hint("о 22:05") == (22, 5)
    assert routines.parse_schedule_hint("без часу") == (8, 0)


# --- гейти ---

async def test_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "enable_routines", False)
    out = await routines.create_routine(7, "context_daily", hour=8)
    assert "ENABLE_ROUTINES" in out["error"]


async def test_missing_host_repo(monkeypatch):
    monkeypatch.setattr(settings, "enable_routines", True)
    monkeypatch.setattr(settings, "routines_host_repo", "")
    out = await routines.create_routine(7, "context_daily", hour=8)
    assert "ROUTINES_HOST_REPO" in out["error"]


async def test_unknown_job_and_bad_time(env):
    assert "невідома" in (await routines.create_routine(7, "bogus", hour=8))["error"]
    assert "hour" in (await routines.create_routine(7, "context_daily", hour=25))["error"]


# --- SY-9.2: матеріалізація ---

async def test_create_routine_materializes_schtasks(env):
    ingest, cli = env
    out = await routines.create_routine(7, "context_daily", hour=8, minute=30, proposal_ref="ctx:5")
    assert out == {
        "job": "context_daily",
        "task": "JARVIS_routine_context_daily",
        "schedule": "DAILY 08:30",
        "status": "active",
    }
    exe, args = cli.calls[0]
    assert exe == "schtasks" and args[0] == "/Create"
    assert "JARVIS_routine_context_daily" in args
    tr = args[args.index("/TR") + 1]
    assert "jarvis_context.py" in tr and "--job daily" in tr and "--url http://127.0.0.1:8000" in tr
    assert args[args.index("/ST") + 1] == "08:30"
    await context_emit.drain()
    st = ingest.stores[0]
    assert st["kind"] == "routine" and "status:active" in st["tags"]
    assert st["ref"] == "ctx:5" and "routine:context_daily" in st["tags"]


async def test_create_failure_no_passport(env, monkeypatch):
    ingest, _ = env
    monkeypatch.setattr(routines, "hostagent_cli", _CliSpy({"stderr": "ДОСТУП", "code": 1}))
    out = await routines.create_routine(7, "context_daily", hour=8)
    assert "failed" in out["error"]
    await context_emit.drain()
    assert ingest.stores == []


async def test_disable_routine(env):
    ingest, cli = env
    out = await routines.disable_routine(7, "context_daily")
    assert out["status"] == "disabled"
    exe, args = cli.calls[0]
    assert args[:2] == ["/Delete", "/TN"] and "JARVIS_routine_context_daily" in args
    await context_emit.drain()
    assert "status:disabled" in ingest.stores[0]["tags"]


# --- список (source of truth = Task Scheduler) ---

async def test_list_routines_parses_csv(env, monkeypatch):
    csv_out = (
        '"\\\\JARVIS_routine_context_daily","07.07.2026 08:30:00","Ready"\n'
        '"\\\\Microsoft\\\\Windows\\\\Foo","N/A","Ready"\n'
        '"\\\\JARVIS_routine_context_retention","07.07.2026 06:00:00","Disabled"\n'
    )
    monkeypatch.setattr(routines, "hostagent_cli", _CliSpy({"stdout": csv_out, "code": 0}))
    out = await routines.list_routines()
    jobs = {r["job"]: r for r in out["routines"]}
    assert set(jobs) == {"context_daily", "context_retention"}
    assert jobs["context_daily"]["status"] == "Ready"
    assert "context_daily" in out["available"]


# --- SY-9.3: run-паспорти ---

async def test_emit_routine_run(env):
    ingest, _ = env
    routines.emit_routine_run(7, "context_daily", {"job": "context_daily", "created": True})
    await context_emit.drain()
    st = ingest.stores[0]
    assert st["kind"] == "routine_run" and "routine:context_daily" in st["tags"]
    assert "created=True" in st["summary"]


async def test_emit_routine_run_flag_off(monkeypatch):
    ingest = _IngestSpy()
    monkeypatch.setattr(context_emit, "_memory", ingest)
    monkeypatch.setattr(settings, "enable_routines", False)
    routines.emit_routine_run(7, "context_daily", {"created": True})
    await context_emit.drain()
    assert ingest.stores == []
