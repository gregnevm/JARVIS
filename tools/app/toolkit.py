"""Інструменти агента: calc, web_search, web_fetch, parse_file, code_exec.

Кожен інструмент — самодостатня функція. I/O-інструменти async (httpx),
решта sync. `dispatch()` — єдина точка виклику за іменем (для агент-лупа).
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("jarvis.tools")

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 JARVIS/1.0"


# --------------------------------------------------------------------------- #
# calc — безпечний матем. калькулятор (simpleeval, без доступу до __builtins__)
# --------------------------------------------------------------------------- #
def calc(expression: str) -> str:
    expression = (expression or "").strip()
    if not expression:
        return "Порожній вираз."
    if len(expression) > 500:
        return "Завеликий вираз."
    try:
        from simpleeval import simple_eval

        result = simple_eval(expression)
    except Exception as exc:  # noqa: BLE001 — повертаємо помилку моделі, не падаємо
        return f"Помилка обчислення: {exc}"
    return str(result)


# --------------------------------------------------------------------------- #
# web_fetch — завантажує URL і витягує читабельний текст
# --------------------------------------------------------------------------- #
def _html_to_text(raw: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except Exception:  # noqa: BLE001 — фолбек без bs4
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def web_fetch(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Некоректний URL (потрібен http/https)."
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=True) as cli:
            resp = await cli.get(url, headers={"User-Agent": _UA})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Не вдалося завантажити сторінку: {exc}"
    text = _html_to_text(resp.text)
    if len(text) > settings.fetch_max_chars:
        text = text[: settings.fetch_max_chars] + " …[обрізано]"
    return text or "Сторінка порожня."


# --------------------------------------------------------------------------- #
# web_search — DuckDuckGo HTML endpoint (без API-ключа)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# parse_file — текст із txt/md/csv/json/log + (lazy) pdf/docx
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# code_exec — Python у subprocess (тільки якщо ENABLE_CODE_EXEC=true)
# --------------------------------------------------------------------------- #
def code_exec(code: str) -> str:
    if not settings.enable_code_exec:
        return "Виконання коду вимкнено (ENABLE_CODE_EXEC=false)."
    code = (code or "").strip()
    if not code:
        return "Порожній код."
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=settings.code_exec_timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Таймаут ({settings.code_exec_timeout}s)."
    out = (proc.stdout or "") + (("\n[stderr] " + proc.stderr) if proc.stderr else "")
    out = out.strip()
    return out[: settings.fetch_max_chars] or "(порожній вивід)"


# --------------------------------------------------------------------------- #
# take_note / recall_notes — персональні нотатки користувача (файл у /data)
# --------------------------------------------------------------------------- #
def _notes_file(user_id: int) -> Path:
    d = Path(settings.data_dir) / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{int(user_id)}.jsonl"


def take_note(text: str, user_id: int) -> str:
    text = (text or "").strip()
    if not text:
        return "Порожня нотатка."
    try:
        rec = {"ts": int(time.time()), "text": text[:2000]}
        with _notes_file(user_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        return f"Не вдалося зберегти нотатку: {exc}"
    return "Нотатку збережено ✅"


def recall_notes(user_id: int, limit: int = 10) -> str:
    limit = max(1, min(limit, 50))
    p = _notes_file(user_id)
    if not p.is_file():
        return "Нотаток поки немає."
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"Не вдалося прочитати нотатки: {exc}"
    out: list[str] = []
    for ln in lines[-limit:]:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        ts = datetime.fromtimestamp(int(rec.get("ts", 0))).strftime("%Y-%m-%d %H:%M")
        out.append(f"• [{ts}] {rec.get('text', '')}")
    return "\n".join(out) if out else "Нотаток поки немає."


# --------------------------------------------------------------------------- #
# Схеми інструментів (OpenAI function format) + диспетчер для агент-лупа
# --------------------------------------------------------------------------- #
def _schema(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


_STR = {"type": "string"}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema("calc", "Обчислити математичний вираз (напр. '17*23', 'sqrt(2)').",
            {"expression": {**_STR, "description": "вираз"}}, ["expression"]),
    _schema("web_search", "Пошук в інтернеті (DuckDuckGo). Повертає топ-результати.",
            {"query": {**_STR, "description": "пошуковий запит"}}, ["query"]),
    _schema("web_fetch", "Завантажити сторінку за URL і повернути її текст.",
            {"url": {**_STR, "description": "повний http(s) URL"}}, ["url"]),
    _schema("take_note", "Зберегти персональну нотатку користувача на майбутнє.",
            {"text": {**_STR, "description": "текст нотатки"}}, ["text"]),
    _schema("recall_notes", "Показати останні збережені нотатки користувача.",
            {}, []),
]

_CODE_SCHEMA = _schema(
    "code_exec", "Виконати короткий Python-скрипт і повернути stdout.",
    {"code": {**_STR, "description": "Python-код"}}, ["code"],
)


def agent_tool_schemas() -> list[dict[str, Any]]:
    """Схеми, які віддаємо моделі. code_exec — лише якщо увімкнено."""
    schemas = list(TOOL_SCHEMAS)
    if settings.enable_code_exec:
        schemas.append(_CODE_SCHEMA)
    return schemas


async def dispatch(name: str, arguments: dict[str, Any], user_id: int = 0) -> str:
    """Викликає інструмент за іменем. Помилки повертаються текстом (модель їх читає).

    user_id потрібен персональним інструментам (нотатки) — пробрасується з агент-лупа.
    """
    try:
        if name == "calc":
            return calc(str(arguments.get("expression", "")))
        if name == "web_search":
            return await web_search(str(arguments.get("query", "")))
        if name == "web_fetch":
            return await web_fetch(str(arguments.get("url", "")))
        if name == "parse_file":
            return parse_file(str(arguments.get("path", "")))
        if name == "code_exec":
            return await asyncio.to_thread(code_exec, str(arguments.get("code", "")))
        if name == "take_note":
            return take_note(str(arguments.get("text", "")), user_id)
        if name == "recall_notes":
            raw_limit = arguments.get("limit", 10)
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                limit = 10
            return recall_notes(user_id, limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s failed", name)
        return f"Інструмент {name} впав: {exc}"
    return f"Невідомий інструмент: {name}"


def coerce_args(raw: Any) -> dict[str, Any]:
    """Аргументи від Ollama бувають dict або JSON-рядком — нормалізуємо в dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
