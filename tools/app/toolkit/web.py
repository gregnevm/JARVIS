"""Web, files, calc, code_exec tools."""
from __future__ import annotations

import html
import re
from pathlib import Path

import httpx

from jarvis_core.safety import exec_guard

from ..config import settings
from . import sandbox

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 JARVIS/1.0"


def calc(expression: str) -> str:
    expression = (expression or "").strip()
    if not expression:
        return "Порожній вираз."
    if len(expression) > 500:
        return "Завеликий вираз."
    try:
        from simpleeval import simple_eval

        result = simple_eval(expression)
    except Exception as exc:  # noqa: BLE001
        return f"Помилка обчислення: {exc}"
    return str(result)


def _html_to_text(raw: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript", "template", "nav", "footer", "header"]):
            tag.decompose()
        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(None, attrs={"role": "main"})
            or soup.find(id="content")
        )
        root = main if main is not None else soup.body or soup
        text = root.get_text(separator=" ")
    except Exception:  # noqa: BLE001
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def web_fetch(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Некоректний URL (потрібен http/https)."
    timeout = httpx.Timeout(
        connect=min(8.0, settings.http_timeout),
        read=settings.http_timeout,
        write=10.0,
        pool=5.0,
    )
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=5) as cli:
            resp = await cli.get(url, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Не вдалося завантажити сторінку: {exc}"
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" not in ctype and "application/xhtml" not in ctype:
        return f"Непідтримуваний тип контенту: {ctype or 'unknown'} (очікується HTML)."
    text = _html_to_text(resp.text)
    if len(text) > settings.fetch_max_chars:
        text = text[: settings.fetch_max_chars] + " …[обрізано]"
    return text or "Сторінка порожня."


async def web_search(query: str, max_results: int = 5) -> str:
    query = (query or "").strip()
    if not query:
        return "Порожній запит."
    max_results = max(1, min(max_results, 10))
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=True) as cli:
            resp = await cli.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": _UA},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Помилка пошуку: {exc}"

    items = _parse_ddg(resp.text, max_results)
    if not items:
        return "Нічого не знайдено."
    lines = [f"{i}. {it['title']}\n   {it['snippet']}\n   {it['url']}" for i, it in enumerate(items, 1)]
    return "\n".join(lines)


def _parse_ddg(raw: str, max_results: int) -> list[dict[str, str]]:
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        return []
    soup = BeautifulSoup(raw, "html.parser")
    out: list[dict[str, str]] = []
    for res in soup.select("div.result")[: max_results * 2]:
        a = res.select_one("a.result__a")
        if a is None:
            continue
        snip = res.select_one(".result__snippet")
        out.append(
            {
                "title": a.get_text(" ", strip=True),
                "url": str(a.get("href", "")).strip(),
                "snippet": snip.get_text(" ", strip=True) if snip else "",
            }
        )
        if len(out) >= max_results:
            break
    return out


_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".py", ".ini", ".yaml", ".yml"}


def parse_file(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        return f"Файл не знайдено: {path}"
    suffix = p.suffix.lower()
    try:
        if suffix in _TEXT_SUFFIXES:
            return p.read_text(encoding="utf-8", errors="replace")[: settings.fetch_max_chars]
        if suffix == ".pdf":
            return _parse_pdf(p)
        if suffix == ".docx":
            return _parse_docx(p)
    except Exception as exc:  # noqa: BLE001
        return f"Помилка читання файлу: {exc}"
    return f"Непідтримуваний формат: {suffix or 'без розширення'}"


def _parse_pdf(p: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001
        return "PDF-парсер недоступний (немає pypdf)."
    reader = PdfReader(str(p))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return text[: settings.fetch_max_chars] or "PDF без текстового шару."


def _parse_docx(p: Path) -> str:
    try:
        import docx
    except Exception:  # noqa: BLE001
        return "DOCX-парсер недоступний (немає python-docx)."
    doc = docx.Document(str(p))
    return "\n".join(par.text for par in doc.paragraphs)[: settings.fetch_max_chars]


def code_exec(code: str) -> str:
    if not settings.enable_code_exec:
        return "Виконання коду вимкнено (ENABLE_CODE_EXEC=false)."
    code = (code or "").strip()
    if not code:
        return "Порожній код."
    allowed, reason = exec_guard.screen(
        code, extra=exec_guard.parse_extra_rules(settings.code_exec_deny_patterns)
    )
    if not allowed:
        return f"Код відхилено guard-правилом ({reason})."
    result = sandbox.run_python(code)
    if isinstance(result, str):
        return result
    out = (result.stdout or "") + (("\n[stderr] " + result.stderr) if result.stderr else "")
    out = out.strip()
    return out[: settings.fetch_max_chars] or "(порожній вивід)"
