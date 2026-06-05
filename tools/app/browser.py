"""C3 Browser — Playwright/CDP (опційно)."""
from __future__ import annotations

import logging
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tools.browser")

_page_url: str = ""
_page = None
_browser = None


def browser_enabled() -> bool:
    return settings.enable_browser


async def _ensure_page() -> Any:
    global _page, _browser, _page_url
    if _page is not None:
        return _page
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright не встановлено (pip install playwright).") from None
    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(headless=True)
    _page = await _browser.new_page()
    return _page


async def browser_open(url: str) -> str:
    if not browser_enabled():
        return "Browser вимкнено (ENABLE_BROWSER=false)."
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Некоректний URL (потрібен http/https)."
    page = await _ensure_page()
    global _page_url
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    _page_url = url
    title = await page.title()
    return f"Відкрито: {title} ({url})"


async def browser_read() -> str:
    if not browser_enabled():
        return "Browser вимкнено."
    if _page is None:
        return "Спочатку browser_open(url)."
    page = _page
    text = await page.evaluate(
        "() => document.body ? document.body.innerText.slice(0, 6000) : ''"
    )
    links = await page.evaluate(
        """() => Array.from(document.querySelectorAll('a, button, input, select'))
        .slice(0, 40).map(el => ({
          tag: el.tagName.toLowerCase(),
          text: (el.innerText || el.value || el.placeholder || '').slice(0, 80),
          sel: el.id ? '#' + el.id : el.name ? el.tagName.toLowerCase() + '[name=\"' + el.name + '\"]' : el.tagName.toLowerCase()
        }))"""
    )
    parts = [f"URL: {_page_url}", f"Текст:\n{text}"]
    if links:
        parts.append("Елементи:")
        for el in links:
            if isinstance(el, dict):
                parts.append(f"  - {el.get('tag')}: {el.get('text')} → {el.get('sel')}")
    return "\n".join(parts)[:8000]


async def browser_click(selector: str) -> str:
    if not browser_enabled() or _page is None:
        return "Browser не готовий."
    await _page.click(selector, timeout=10000)
    return f"Клік: {selector}"


async def browser_fill(selector: str, value: str) -> str:
    if not browser_enabled() or _page is None:
        return "Browser не готовий."
    await _page.fill(selector, value, timeout=10000)
    return f"Заповнено {selector}"


async def browser_eval(js: str) -> str:
    if not browser_enabled() or _page is None:
        return "Browser не готовий."
    result = await _page.evaluate(js)
    return str(result)[:6000]
