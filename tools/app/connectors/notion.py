"""Notion connector (P6) — search/read via integration token."""
from __future__ import annotations

from typing import Any

import httpx

from ..config import settings

_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"


def is_configured() -> bool:
    return bool((settings.notion_token or "").strip())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.notion_token.strip()}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    }


async def search(query: str, *, limit: int = 5) -> str:
    if not is_configured():
        return "Notion не налаштовано (NOTION_TOKEN у .env)."
    query = (query or "").strip()
    if not query:
        return "Порожній запит."
    body: dict[str, Any] = {"query": query, "page_size": max(1, min(limit, 10))}
    db = (settings.notion_database_id or "").strip()
    if db:
        body["filter"] = {"value": "page", "property": "object"}
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as cli:
            resp = await cli.post(f"{_API}/search", headers=_headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return f"Notion помилка: {exc}"
    results = data.get("results") if isinstance(data, dict) else []
    if not results:
        return "Нічого не знайдено в Notion."
    lines: list[str] = []
    for i, item in enumerate(results[:limit], 1):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "")
        title = _page_title(item)
        lines.append(f"{i}. {title} (id={pid})")
    return "\n".join(lines)


def _page_title(page: dict[str, Any]) -> str:
    raw_props = page.get("properties")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    for val in props.values():
        if isinstance(val, dict) and val.get("type") == "title":
            arr = val.get("title") or []
            if arr and isinstance(arr[0], dict):
                return str(arr[0].get("plain_text") or "Untitled")
    return str(page.get("url") or "Untitled")


async def read_page(page_id: str) -> str:
    if not is_configured():
        return "Notion не налаштовано (NOTION_TOKEN у .env)."
    page_id = (page_id or "").strip().replace("-", "")
    if not page_id:
        return "page_id required"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as cli:
            resp = await cli.get(f"{_API}/pages/{page_id}", headers=_headers())
            resp.raise_for_status()
            page = resp.json()
            blocks = await cli.get(
                f"{_API}/blocks/{page_id}/children", headers=_headers(), params={"page_size": 30}
            )
            blocks.raise_for_status()
            children = blocks.json()
    except httpx.HTTPError as exc:
        return f"Notion read error: {exc}"
    title = _page_title(page if isinstance(page, dict) else {})
    texts: list[str] = [f"# {title}"]
    for block in (children.get("results") if isinstance(children, dict) else []) or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        payload = block.get(btype) if isinstance(block.get(btype), dict) else {}
        if isinstance(payload, dict) and payload.get("rich_text"):
            for rt in payload["rich_text"]:
                if isinstance(rt, dict):
                    texts.append(str(rt.get("plain_text") or ""))
    body = "\n".join(texts)
    return body[: settings.fetch_max_chars] if len(body) > settings.fetch_max_chars else body
