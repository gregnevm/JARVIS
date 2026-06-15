"""Cursor IDE tasks — local host agent або Cloud Agents API."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("jarvis.tools.cursor_tasks")


def _enabled() -> bool:
    return bool(settings.cursor_tasks_enabled)


def _inbox_dir() -> Path:
    p = Path(settings.data_dir) / "cursor" / "inbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _queue_inbox(task: str, *, user_id: int, mode: str) -> dict[str, Any]:
    task_id = uuid.uuid4().hex[:12]
    rec = {
        "id": task_id,
        "user_id": user_id,
        "task": task,
        "mode": mode,
        "created_at": int(time.time()),
        "status": "queued",
    }
    path = _inbox_dir() / f"{task_id}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "mode": "inbox",
        "task_id": task_id,
        "path": str(path),
        "message": (
            f"Задачу збережено в inbox ({path.name}). "
            "Встанови cursor-sdk на хості: pip install cursor-sdk && CURSOR_API_KEY=…"
        ),
    }


async def _run_local_host(task: str) -> dict[str, Any]:
    from .computer import _run_cli_impl

    script = (settings.cursor_host_script or "").strip()
    workspace = (settings.cursor_host_workspace or "").strip()
    if not script or not workspace:
        return {"ok": False, "error": "CURSOR_HOST_SCRIPT / CURSOR_HOST_WORKSPACE не задані"}
    args = [
        script,
        "--task",
        task,
        "--cwd",
        workspace,
        "--model",
        (settings.cursor_model or "composer-2.5").strip(),
    ]
    if settings.cursor_api_key:
        args.extend(["--api-key", settings.cursor_api_key.strip()])
    out = await _run_cli_impl(
        settings.cursor_python_exe or "python",
        args,
        workspace,
        trusted=True,
    )
    ok = "[exit 0]" in out
    return {"ok": ok, "mode": "local", "output": out}


async def _poll_cloud_run(
    client: httpx.AsyncClient,
    agent_id: str,
    run_id: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    base = settings.cursor_api_base.rstrip("/")
    auth = (settings.cursor_api_key, "")
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        r = await client.get(f"{base}/v1/agents/{agent_id}/runs/{run_id}", auth=auth)
        r.raise_for_status()
        last = r.json()
        status = str(last.get("status") or "").upper()
        if status in {"FINISHED", "FAILED", "CANCELLED", "ERROR"}:
            return last
        await asyncio.sleep(5.0)
    return {**last, "status": "TIMEOUT", "error": f"poll timeout ({timeout}s)"}


async def _run_cloud(task: str) -> dict[str, Any]:
    key = (settings.cursor_api_key or "").strip()
    repo = (settings.cursor_repo_url or "").strip()
    if not key:
        return {"ok": False, "error": "CURSOR_API_KEY не заданий"}
    if not repo:
        return {"ok": False, "error": "CURSOR_REPO_URL потрібен для cloud mode"}
    payload: dict[str, Any] = {
        "prompt": {"text": task},
        "model": {"id": settings.cursor_model or "composer-2.5"},
        "repos": [{"url": repo, "startingRef": settings.cursor_repo_ref or "main"}],
        "autoCreatePR": settings.cursor_auto_create_pr,
    }
    base = settings.cursor_api_base.rstrip("/")
    timeout = httpx.Timeout(settings.cursor_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{base}/v1/agents", json=payload, auth=(key, ""))
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:500], "status": r.status_code}
        data = r.json()
        agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
        run = data.get("run") if isinstance(data.get("run"), dict) else {}
        agent_id = str(agent.get("id") or data.get("id") or "")
        run_id = str(run.get("id") or data.get("runId") or "")
        if not agent_id or not run_id:
            return {"ok": False, "error": "unexpected cloud API response", "raw": data}
        final = await _poll_cloud_run(
            client, agent_id, run_id, timeout=float(settings.cursor_timeout)
        )
        status = str(final.get("status") or "").upper()
        text = str(final.get("text") or final.get("result") or "")
        ok = status == "FINISHED"
        return {
            "ok": ok,
            "mode": "cloud",
            "agent_id": agent_id,
            "run_id": run_id,
            "status": status,
            "result": text[:8000],
            "error": "" if ok else str(final.get("error") or status),
        }


async def execute(task: str, *, user_id: int = 0) -> dict[str, Any]:
    """Синхронне виконання Cursor-задачі."""
    task = (task or "").strip()
    if not task:
        return {"ok": False, "error": "empty task"}
    if not _enabled():
        return {"ok": False, "error": "cursor tasks disabled (CURSOR_TASKS_ENABLED=false)"}

    mode = (settings.cursor_runtime or "local").strip().lower()
    if mode == "cloud":
        result = await _run_cloud(task)
        if result.get("ok"):
            return result
        if settings.cursor_fallback_inbox:
            inbox = _queue_inbox(task, user_id=user_id, mode="cloud-fallback")
            inbox["cloud_error"] = result.get("error")
            return inbox
        return result

    if settings.enable_computer_use:
        result = await _run_local_host(task)
        if result.get("ok"):
            return result
        if settings.cursor_fallback_inbox:
            inbox = _queue_inbox(task, user_id=user_id, mode="local-fallback")
            inbox["host_error"] = result.get("output") or result.get("error")
            return inbox
        return result

    if (settings.cursor_api_key or "").strip() and (settings.cursor_repo_url or "").strip():
        return await _run_cloud(task)
    return _queue_inbox(task, user_id=user_id, mode="inbox")


async def submit(user_id: int, task: str, *, async_mode: bool = True) -> dict[str, Any]:
    """Поставити задачу в чергу (bg job) або виконати одразу."""
    task = (task or "").strip()
    if not task:
        return {"ok": False, "error": "empty task"}
    if async_mode:
        from . import bg_jobs

        job = await bg_jobs.create_typed_job(user_id, "cursor_task", {"task": task})
        return {"ok": True, "async": True, "job_id": job["id"], "status": job["status"]}
    result = await execute(task, user_id=user_id)
    return result


def format_result(result: dict[str, Any]) -> str:
    if result.get("async"):
        return f"🧠 Cursor задача в черзі: job {result.get('job_id')}"
    if result.get("ok"):
        mode = result.get("mode", "?")
        if mode == "cloud":
            body = str(result.get("result") or "")[:3500]
            return f"✅ Cursor cloud ({result.get('status')}):\n{body or '(без тексту)'}"
        if mode == "inbox":
            return f"📥 {result.get('message', 'inbox')}"
        return f"✅ Cursor local:\n{str(result.get('output') or '')[:3500]}"
    err = str(result.get("error") or result.get("host_error") or result.get("cloud_error") or "failed")
    return f"❌ Cursor: {err[:500]}"
