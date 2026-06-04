"""Веб-панель адміна JARVIS — /admin з HTTP Basic Auth."""
from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from .access_store import AccessStore, UserRecord
from .auth import allowed_ids_snapshot, computer_owner_ids
from .bot.admin import execute_action
from .config import settings
from .health_watch import _fetch_stack, _labels, _load_state
from .services import ServicesClient

logger = logging.getLogger("jarvis.gateway.admin_panel")

router = APIRouter()
_security = HTTPBasic(auto_error=False)

_INDEX = Path(__file__).parent / "static" / "admin.html"
def panel_enabled() -> bool:
    return bool(settings.admin_panel_password.strip())


def _check_credentials(username: str, password: str) -> bool:
    want_user = settings.admin_panel_user.strip() or "admin"
    want_pass = settings.admin_panel_password
    if not want_pass:
        return False
    user_ok = secrets.compare_digest(username.encode(), want_user.encode())
    pass_ok = secrets.compare_digest(password.encode(), want_pass.encode())
    return user_ok and pass_ok


def require_panel_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> None:
    if not panel_enabled():
        raise HTTPException(
            status_code=503,
            detail="Admin panel disabled — set ADMIN_PANEL_PASSWORD in .env",
        )
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": 'Basic realm="JARVIS Admin"'},
        )
    if not _check_credentials(credentials.username, credentials.password):
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="JARVIS Admin"'},
        )


def _primary_admin_id() -> int:
    ids = sorted(settings.admin_ids)
    return ids[0] if ids else 0


def _user_json(rec: UserRecord) -> dict[str, Any]:
    return {
        "user_id": rec.user_id,
        "username": rec.username,
        "first_name": rec.first_name,
        "last_name": rec.last_name,
        "label": _format_label(rec),
    }


def _format_label(rec: UserRecord) -> str:
    parts: list[str] = []
    if rec.first_name:
        parts.append(str(rec.first_name))
    if rec.last_name:
        parts.append(str(rec.last_name))
    name = " ".join(parts).strip() or "—"
    uname = f"@{rec.username}" if rec.username else "без username"
    return f"{name} ({uname})"


def _flag(on: bool) -> dict[str, Any]:
    return {"on": on, "label": "увімкнено" if on else "вимкнено"}


def _settings_snapshot(dash: dict[str, Any]) -> dict[str, Any]:
    """Read-only знімок .env-налаштувань (зміни — через .env + recreate)."""
    return {
        "telegram": {
            "ingest_mode": settings.telegram_ingest_mode,
            "reply_keyboard": _flag(settings.telegram_reply_keyboard),
            "public_app_url": settings.public_app_url or "—",
            "webapp_dev_open": _flag(settings.webapp_dev_open),
            "webhook_configured": bool(settings.telegram_webhook_url.strip()),
        },
        "agent": {
            "env_mode": dash.get("agent_mode_env") or dash.get("agent_mode"),
            "runtime_mode": dash.get("agent_mode"),
            "agent_timeout_s": settings.agent_timeout,
            "max_agent_iters": dash.get("max_agent_iters"),
            "computer_max_iters": dash.get("computer_max_iters"),
            "streaming": _flag(settings.enable_streaming),
            "voice_reply": _flag(settings.enable_voice_reply),
            "reaction_replies": _flag(settings.enable_reaction_replies),
        },
        "limits": {
            "rate_limit_per_min": settings.rate_limit_per_min,
            "guest_rate_limit_per_min": settings.guest_rate_limit_per_min or settings.rate_limit_per_min,
            "album_collect_seconds": settings.album_collect_seconds,
            "remote_file_max_mb": round(settings.remote_file_max_bytes / (1024 * 1024), 1),
        },
        "computer": {
            "enable_computer_use": _flag(bool(dash.get("enable_computer_use"))),
            "hostagent_up": _flag(bool(dash.get("hostagent_up"))),
            "docker_up": _flag(bool(dash.get("docker_up"))),
            "code_exec": _flag(bool(dash.get("code_exec"))),
            "enable_browser": _flag(bool(dash.get("enable_browser"))),
            "computer_require_confirm": _flag(bool(dash.get("computer_require_confirm", True))),
            "computer_auto_vision": _flag(bool(dash.get("computer_auto_vision", True))),
            "computer_allow_power": _flag(bool(dash.get("computer_allow_power"))),
            "computer_owner_ids": sorted(computer_owner_ids()),
            "hostagent_drop_dir": settings.hostagent_drop_dir or "—",
        },
        "models": {
            "ollama_host": dash.get("ollama_host") or "—",
            "chat_model": dash.get("chat_model"),
            "agent_model": dash.get("agent_model"),
            "vision_model": dash.get("vision_model") or "—",
            "embed_model": dash.get("embed_model") or "—",
            "image_gen": dash.get("image_gen") or "—",
        },
        "health": {
            "watch_interval_s": settings.health_watch_interval,
            "alert_user_ids": sorted(settings.health_alert_ids) or sorted(computer_owner_ids()),
            "reminder_poll_s": settings.reminder_poll_seconds,
            "ignore_edited_messages": _flag(settings.ignore_edited_messages),
        },
        "access": {
            "admin_ids": sorted(settings.admin_ids),
            "env_whitelist_count": len(settings.allowed_ids),
            "access_store": settings.access_store_path,
        },
    }


async def _probe_url(client: httpx.AsyncClient, name: str, url: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = await client.get(url)
        ms = int((time.perf_counter() - t0) * 1000)
        return {"name": name, "ok": r.status_code < 400, "status": r.status_code, "ms": ms}
    except httpx.HTTPError as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        return {"name": name, "ok": False, "status": 0, "ms": ms, "error": str(exc)[:120]}


async def _safe_health_prev(redis: aioredis.Redis) -> dict[str, bool]:
    try:
        return await _load_state(redis)
    except Exception as exc:  # noqa: BLE001
        logger.debug("health prev load failed: %s", exc)
        return {}


async def probe_services() -> list[dict[str, Any]]:
    probes = [
        ("gateway", "http://127.0.0.1:8000/health"),
        ("tools", f"{settings.tools_url.rstrip('/')}/health"),
        ("memory", f"{settings.memory_url.rstrip('/')}/health"),
        ("twin", f"{settings.twin_url.rstrip('/')}/health"),
        ("whisper", f"{settings.whisper_url.rstrip('/')}/health"),
    ]
    if settings.enable_voice_reply:
        probes.append(("tts", f"{settings.tts_url.rstrip('/')}/health"))
    async with httpx.AsyncClient(timeout=4.0) as client:
        out: list[dict[str, Any]] = []
        for name, url in probes:
            out.append(await _probe_url(client, name, url))
        return out


def _enrich_dashboard(dash: dict[str, Any]) -> dict[str, Any]:
    """Додає поля з tools dashboard для панелі (якщо є в status)."""
    if dash.get("error"):
        return dash
    # Підтягнемо з tools status окремих ключів через dashboard payload
    return dash


class ModeBody(BaseModel):
    mode: str


class UserIdBody(BaseModel):
    user_id: int = Field(..., gt=0)


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(_: None = Depends(require_panel_auth)) -> HTMLResponse:
    try:
        return HTMLResponse(_INDEX.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="admin UI not built") from None


@router.get("/admin/api/overview")
async def admin_overview(request: Request, _: None = Depends(require_panel_auth)) -> dict[str, Any]:
    svc: ServicesClient = request.app.state.svc
    store: AccessStore = request.app.state.access_store
    redis: aioredis.Redis = request.app.state.redis
    dash = _enrich_dashboard(await svc.dashboard())
    twin = await svc.twin_status()
    stack = await _fetch_stack(svc)
    health_prev = await _safe_health_prev(redis)
    services = await probe_services()
    tools: Any = request.app.state.tools
    admin_id = _primary_admin_id()
    remote: dict[str, Any] = {}
    jobs: list[dict[str, Any]] = []
    try:
        if admin_id:
            remote = await tools.remote_status(admin_id)
        jobs = await tools.due_jobs()
    except Exception as exc:  # noqa: BLE001
        logger.debug("operations fetch failed: %s", exc)
    return {
        "ok": not dash.get("error"),
        "core": dash,
        "twin": twin,
        "stack": {k: {"ok": v, "label": _labels().get(k, k)} for k, v in stack.items()},
        "health_prev": health_prev,
        "services": services,
        "settings": _settings_snapshot(dash),
        "access": {
            "pending": [_user_json(r) for r in store.list_pending()],
            "approved": [_user_json(r) for r in store.list_approved()],
            "env_whitelist": sorted(settings.allowed_ids),
            "dynamic_whitelist": sorted(allowed_ids_snapshot()),
            "admin_ids": sorted(settings.admin_ids),
        },
        "operations": {
            "computer_pending": remote.get("pending"),
            "computer_audit": (remote.get("audit") or {}).get("entries") or [],
            "due_jobs": jobs[:20],
        },
        "links": {
            "mini_app": settings.public_app_url or "/app",
            "admin_panel": "/admin",
        },
        "ts": int(time.time()),
    }


@router.get("/admin/api/health")
async def admin_health(request: Request, _: None = Depends(require_panel_auth)) -> dict[str, Any]:
    svc: ServicesClient = request.app.state.svc
    redis: aioredis.Redis = request.app.state.redis
    stack = await _fetch_stack(svc)
    return {
        "stack": stack,
        "labels": _labels(),
        "prev": await _safe_health_prev(redis),
        "services": await probe_services(),
        "ts": int(time.time()),
    }


@router.post("/admin/api/mode")
async def admin_set_mode(
    body: ModeBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    mode = body.mode.lower().strip()
    if mode not in {"chat", "agent", "hybrid", "computer"}:
        raise HTTPException(status_code=400, detail="bad mode")
    return await request.app.state.svc.set_mode(mode)


@router.delete("/admin/api/mode")
async def admin_reset_mode(
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    return await request.app.state.svc.reset_mode()


@router.post("/admin/api/access/approve")
async def admin_approve(
    body: UserIdBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    store: AccessStore = request.app.state.access_store
    uid = body.user_id
    if uid in settings.allowed_ids:
        return {"ok": False, "message": "already in .env whitelist"}
    ok, msg, rec = await store.approve(uid, by_admin=_primary_admin_id())
    if not ok:
        return {"ok": False, "message": msg}
    tg = request.app.state.tg
    if rec is not None:
        try:
            await tg.send_message(
                uid,
                "✅ <b>Доступ відкрито!</b>\n\nНапиши /start — можна користуватись JARVIS.",
                parse_mode="HTML",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("approve notify %s failed: %s", uid, exc)
    return {"ok": True, "user": _user_json(rec) if rec else {"user_id": uid}}


@router.post("/admin/api/access/deny")
async def admin_deny(
    body: UserIdBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    store: AccessStore = request.app.state.access_store
    ok, msg = await store.deny(body.user_id)
    return {"ok": ok, "message": msg}


@router.post("/admin/api/access/revoke")
async def admin_revoke(
    body: UserIdBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    uid = body.user_id
    if uid in settings.allowed_ids:
        return {"ok": False, "message": "remove from ALLOWED_USER_IDS in .env"}
    store: AccessStore = request.app.state.access_store
    ok, msg = await store.revoke(uid)
    if ok:
        tg = request.app.state.tg
        try:
            await tg.send_message(uid, "Доступ до JARVIS закрито.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("revoke notify %s failed: %s", uid, exc)
    return {"ok": ok, "message": msg}


@router.post("/admin/api/ratelimit/reset")
async def admin_reset_rl(
    body: UserIdBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, Any]:
    redis: aioredis.Redis = request.app.state.redis
    action = f"rl:{body.user_id}"
    text = await execute_action(action, request.app.state.svc, redis)
    return {"ok": "✅" in text, "message": text}


@router.post("/admin/api/computer/trust")
async def admin_computer_trust(
    body: UserIdBody,
    request: Request,
    _: None = Depends(require_panel_auth),
) -> dict[str, str]:
    await request.app.state.tools.grant_trust(body.user_id)
    return {"status": "trusted"}
