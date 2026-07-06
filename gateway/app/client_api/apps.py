"""APK-apps — артефакти, заточені під мобільний клієнт (Стовп C).

Кожен apk-app = self-contained web-бандл (один HTML+JS), що зберігається на сервері й
рендериться у WebView застосунку. Ключове: **оновлення всередині додатку без перевстановлення
APK** — клієнт щоразу тягне свіжий бандл із `/api/v1/apps/{id}/bundle`. Може бути будь-чим
(гра, інструмент, дашборд) і через JS-міст звертатися до функцій телефона.

Стор — файловий: `{data_dir}/apps/{uid}/{id}/` (manifest.json + index.html). Org-scoped по uid.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from ..config import settings
from .deps import context_uid as _uid
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.apps")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class AppBody(BaseModel):
    name: str
    html: str
    version: str = ""


def _apps_root(uid: int) -> Path:
    return Path(settings.data_dir) / "apps" / str(uid)


def _safe_id(app_id: str) -> str:
    aid = (app_id or "").strip().lower()
    if not _ID_RE.match(aid):
        raise HTTPException(status_code=400, detail="invalid app id (a-z0-9_-)")
    return aid


def _read_manifest(d: Path) -> dict[str, Any]:
    try:
        return dict(json.loads((d / "manifest.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def register(router: APIRouter) -> None:
    @router.get("/apps")
    async def apps_list(ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        root = _apps_root(_uid(ctx))
        items: list[dict[str, Any]] = []
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "index.html").is_file():
                    m = _read_manifest(d)
                    items.append({"id": d.name, "name": m.get("name") or d.name,
                                  "version": m.get("version") or "1", "updated": m.get("updated")})
        return {"apps": items}

    @router.get("/apps/{app_id}")
    async def app_manifest(app_id: str,
                           ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        d = _apps_root(_uid(ctx)) / _safe_id(app_id)
        if not (d / "index.html").is_file():
            raise HTTPException(status_code=404, detail="app not found")
        m = _read_manifest(d)
        return {"id": d.name, **m}

    @router.post("/apps/{app_id}")
    async def app_upsert(app_id: str, body: AppBody,
                         ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Створити/оновити бандл (авторинг із чату/артефактів). Версія авто-інкремент."""
        aid = _safe_id(app_id)
        d = _apps_root(_uid(ctx)) / aid
        d.mkdir(parents=True, exist_ok=True)
        prev = _read_manifest(d)
        if body.version.strip():
            version = body.version.strip()
        elif str(prev.get("version", "")).isdigit():
            version = str(int(prev["version"]) + 1)  # авто-інкремент
        else:
            version = "1"
        (d / "index.html").write_text(body.html, encoding="utf-8")
        manifest = {"name": body.name, "version": version, "updated": int(time.time())}
        (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return {"id": aid, **manifest}

    @router.get("/apps/{app_id}/bundle", response_class=HTMLResponse)
    async def app_bundle(app_id: str,
                         ctx: RequestContext = Depends(resolve_client_context)) -> HTMLResponse:
        """HTML-бандл для WebView. Завжди свіжий → оновлення без перевстановлення APK."""
        d = _apps_root(_uid(ctx)) / _safe_id(app_id)
        f = d / "index.html"
        if not f.is_file():
            raise HTTPException(status_code=404, detail="app not found")
        return HTMLResponse(f.read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store"})

    @router.delete("/apps/{app_id}")
    async def app_delete(app_id: str,
                         ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        import shutil
        d = _apps_root(_uid(ctx)) / _safe_id(app_id)
        if not d.is_dir():
            raise HTTPException(status_code=404, detail="app not found")
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True}
