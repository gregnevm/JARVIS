"""Deep Research (P4) — multi-hop web search + synthesis with citations."""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .config import settings
from .toolkit import web_fetch, web_search

ProgressFn = Callable[[int, str], Awaitable[None]] | None

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _parse_urls_from_search(text: str, limit: int) -> list[str]:
    urls: list[str] = []
    for line in (text or "").splitlines():
        m = _URL_RE.search(line)
        if m:
            u = m.group(0).rstrip(").,;")
            if u not in urls:
                urls.append(u)
        if len(urls) >= limit:
            break
    return urls


async def _noop_progress(_pct: int, _msg: str) -> None:
    pass


async def deep_research(
    query: str,
    *,
    max_hops: int | None = None,
    urls_per_hop: int = 3,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    """Multi-hop research → markdown report + sources list."""
    prog = progress or _noop_progress
    query = (query or "").strip()
    if not query:
        return {"report": "Порожній запит.", "sources": []}

    hops = max(1, min(max_hops or settings.research_max_hops, settings.research_max_hops))
    url_cap = max(1, min(urls_per_hop, settings.research_max_urls))
    sources: list[dict[str, str]] = []
    snippets: list[str] = []
    current_query = query

    await prog(5, "Початок дослідження")

    for hop in range(hops):
        pct_base = 10 + hop * (70 // hops)
        await prog(pct_base, f"Пошук (hop {hop + 1}): {current_query[:80]}")
        search_text = await web_search(current_query, max_results=url_cap + 2)
        snippets.append(f"## Hop {hop + 1} query: {current_query}\n{search_text[:3000]}")
        urls = _parse_urls_from_search(search_text, url_cap)
        if not urls:
            break

        fetched: list[str] = []
        for url in urls:
            if any(s.get("url") == url for s in sources):
                continue
            text = await web_fetch(url)
            idx = len(sources) + 1
            sources.append({"id": str(idx), "url": url, "title": url[:120]})
            fetched.append(f"[{idx}] {url}\n{text[: settings.research_max_chars // max(hops, 1)]}")
        snippets.extend(fetched)
        await prog(pct_base + 15, f"Завантажено {len(fetched)} сторінок")

        if hop + 1 >= hops:
            break
        # Follow-up query heuristic (no extra LLM call on MVP — expand from snippets)
        words = re.findall(r"\w{4,}", " ".join(fetched)[:2000], re.UNICODE)
        if words:
            extra = " ".join(sorted(set(words), key=words.count, reverse=True)[:3])
            current_query = f"{query} {extra}"[:200]
        else:
            break

    await prog(85, "Синтез звіту")
    report = _synthesize_report(query, snippets, sources)
    await prog(100, "Готово")
    return {"report": report, "sources": sources, "query": query}


def _synthesize_report(query: str, snippets: list[str], sources: list[dict[str, str]]) -> str:
    """Markdown report with citation markers (MVP template synthesis)."""
    lines = [f"# Deep Research: {query}", ""]
    if sources:
        lines.append("## Джерела")
        for s in sources:
            lines.append(f"- [{s['id']}] {s['url']}")
        lines.append("")
    lines.append("## Знайдене")
    body = "\n\n".join(snippets)[: settings.research_max_chars]
    # Insert citation refs where URLs appear
    for s in sources:
        body = body.replace(s["url"], f"{s['url']} [{s['id']}]")
    lines.append(body[:8000])
    lines.append("")
    lines.append("_Звіт згенеровано JARVIS Deep Research (multi-hop)._")
    return "\n".join(lines)


async def deep_research_with_llm(
    query: str,
    llm_chat: Any,
    *,
    max_hops: int | None = None,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    """Optional LLM synthesis pass over collected snippets."""
    base = await deep_research(query, max_hops=max_hops, progress=progress)
    snippets = base.get("report", "")
    sources = base.get("sources") or []
    if not llm_chat or not snippets:
        return base
    src_json = json.dumps(sources, ensure_ascii=False)
    prompt = (
        "На основі дослідницьких нотаток напиши звіт українською з цитуваннями [1][2].\n"
        f"Запит: {query}\nДжерела JSON: {src_json}\nНотатки:\n{snippets[:12000]}"
    )
    try:
        msg = await llm_chat.chat(
            settings.ollama_model_agent,
            [
                {"role": "system", "content": "Ти дослідник. Дай структурований звіт з citations."},
                {"role": "user", "content": prompt},
            ],
        )
        report = (msg.get("content") or "").strip()
        if report:
            base["report"] = report
    except Exception:  # noqa: BLE001
        pass
    return base
