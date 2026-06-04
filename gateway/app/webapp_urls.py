"""Нормалізація URL Telegram Mini App (/app)."""
from __future__ import annotations


def normalize_mini_app_url(raw: str) -> str:
    """Повертає https://…/app або порожній рядок."""
    url = (raw or "").strip()
    if not url.startswith("https://"):
        return ""
    base = url.rstrip("/")
    if base.endswith("/admin"):
        return base
    if not base.endswith("/app"):
        base = f"{base}/app"
    return base


def local_app_url(browser_root: str, *, canvas: bool = False) -> str:
    """URL для локального браузера (WEBAPP_DEV_OPEN)."""
    root = (browser_root or "http://127.0.0.1:8000").strip().rstrip("/")
    url = f"{root}/app"
    if canvas:
        url += "?canvas=1"
    return url
