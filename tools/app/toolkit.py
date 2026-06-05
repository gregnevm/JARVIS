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
        for tag in soup(["script", "style", "noscript", "template", "nav", "footer", "header"]):
            tag.decompose()
        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(id="content")
        )
        root = main if main is not None else soup.body or soup
        text = root.get_text(separator=" ")
    except Exception:  # noqa: BLE001 — фолбек без bs4
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
# ocr_image — текст із зображення (tesseract через pytesseract). Lazy + graceful.
# --------------------------------------------------------------------------- #
def ocr_image(path: str, lang: str = "ukr+eng") -> str:
    p = Path(path)
    if not p.is_file():
        return f"Файл не знайдено: {path}"
    try:
        import pytesseract
        from PIL import Image
    except Exception:  # noqa: BLE001
        return "OCR недоступний (немає pytesseract/Pillow або системного tesseract)."
    try:
        with Image.open(str(p)) as img:
            text = pytesseract.image_to_string(img, lang=lang)
    except Exception as exc:  # noqa: BLE001
        # Часта причина — не встановлений мовний пакет; пробуємо англійською.
        try:
            with Image.open(str(p)) as img:
                text = pytesseract.image_to_string(img)
        except Exception:  # noqa: BLE001
            return f"Помилка OCR: {exc}"
    text = (text or "").strip()
    return text[: settings.fetch_max_chars] or "На зображенні не знайдено тексту."


# --------------------------------------------------------------------------- #
# describe_image — опис зображення vision-моделлю Ollama (llava/qwen-vl тощо).
# --------------------------------------------------------------------------- #
async def describe_image(path: str, question: str = "") -> str:
    if not settings.ollama_model_vision:
        return "Опис зображень вимкнено (не задано OLLAMA_MODEL_VISION)."
    p = Path(path)
    if not p.is_file():
        return f"Файл не знайдено: {path}"
    import base64

    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError as exc:
        return f"Не вдалося прочитати зображення: {exc}"
    from .ollama_vram import vision_chat_payload, vision_vram_scope

    prompt = question.strip() or "Опиши детально, що зображено. Якщо є текст — наведи його."
    payload = vision_chat_payload(prompt, b64)
    try:
        async with vision_vram_scope():
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as cli:
                resp = await cli.post(
                    f"{settings.ollama_host.rstrip('/')}/api/chat", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"Vision-модель недоступна: {exc}"
    msg = data.get("message") or {}
    text = str(msg.get("content") or "").strip()
    return text[: settings.fetch_max_chars] or "Vision-модель не дала опису."


# --------------------------------------------------------------------------- #
# generate_image — Ollama (txt2img), A1111/Forge або OpenAI-сумісний бекенд.
# --------------------------------------------------------------------------- #
def image_gen_enabled() -> bool:
    """Чи доступний інструмент generate_image (схема + dispatch)."""
    url = (settings.image_gen_url or "").strip().lower()
    if url in ("ollama", "ollama://"):
        return bool((settings.image_gen_model or "").strip())
    if url in ("pollinations", "pollinations.ai"):
        return True
    if url in ("horde", "aihorde", "stablehorde"):
        return True
    return bool(url)


def _image_gen_backend() -> str:
    url = (settings.image_gen_url or "").strip().lower()
    if url in ("ollama", "ollama://"):
        return "ollama"
    if url in ("pollinations", "pollinations.ai"):
        return "pollinations"
    if url in ("horde", "aihorde", "stablehorde"):
        return "horde"
    if "/v1" in url:
        return "openai"
    return "a1111"


def _save_generated_png(img_bytes: bytes) -> Path | str:
    out_dir = Path(settings.data_dir) / "uploads"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"gen_{int(time.time())}.png"
    out.write_bytes(img_bytes)
    return out


_HORDE_API = "https://aihorde.net/api/v2"
_HORDE_AGENT = "JARVIS:1.0:jarvis-telegram"


def _horde_headers() -> dict[str, str]:
    return {
        "apikey": (settings.horde_api_key or "0000000000").strip(),
        "Client-Agent": _HORDE_AGENT,
    }


async def _generate_image_horde(prompt: str) -> bytes | None:
    import base64

    models = ["AlbedoBase XL (SDXL)", "Deliberate", "DreamShaper"]
    if (settings.image_gen_model or "").strip():
        models = [settings.image_gen_model.strip()]
    body = {
        "prompt": prompt,
        "params": {"width": 512, "height": 512, "steps": 22, "n": 1},
        "models": models,
        "r2": True,
        "nsfw": False,
        "censor_nsfw": True,
    }
    deadline = time.monotonic() + settings.image_gen_timeout
    async with httpx.AsyncClient(timeout=60.0) as cli:
        resp = await cli.post(
            f"{_HORDE_API}/generate/async",
            json=body,
            headers=_horde_headers(),
        )
        resp.raise_for_status()
        job_id = resp.json().get("id")
        if not job_id:
            return None
        while time.monotonic() < deadline:
            chk = await cli.get(
                f"{_HORDE_API}/generate/check/{job_id}",
                headers=_horde_headers(),
            )
            chk.raise_for_status()
            if chk.json().get("done"):
                break
            await asyncio.sleep(2.0)
        st = await cli.get(
            f"{_HORDE_API}/generate/status/{job_id}",
            headers=_horde_headers(),
        )
        st.raise_for_status()
        gens = st.json().get("generations") or []
        if not gens:
            return None
        gen = gens[0]
        img_url = gen.get("img")
        if img_url:
            img_resp = await cli.get(str(img_url))
            img_resp.raise_for_status()
            return img_resp.content
        raw_b64 = gen.get("base64") or gen.get("imgdata")
        if raw_b64:
            return base64.b64decode(raw_b64)
    return None


async def _generate_image_pollinations(prompt: str) -> bytes | None:
    from urllib.parse import quote

    # Без API-ключа; запит іде в інтернет (не повністю локально).
    url = (
        "https://image.pollinations.ai/prompt/"
        f"{quote(prompt)}?width=768&height=768&nologo=true"
    )
    async with httpx.AsyncClient(timeout=settings.image_gen_timeout, follow_redirects=True) as cli:
        resp = await cli.get(url)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "image" not in ctype:
            return None
        return resp.content


async def _generate_image_ollama(prompt: str) -> bytes | None:
    import base64

    model = (settings.image_gen_model or "x/z-image-turbo").strip()
    url = f"{settings.ollama_host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    async with httpx.AsyncClient(timeout=settings.image_gen_timeout) as cli:
        resp = await cli.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("image")
    if isinstance(raw, str) and raw:
        return base64.b64decode(raw)
    # NDJSON (stream=true fallback): останній рядок з image
    text = resp.text.strip()
    if text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw = chunk.get("image")
            if isinstance(raw, str) and raw:
                return base64.b64decode(raw)
    return None


async def generate_image(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not image_gen_enabled():
        return (
            "Генерація зображень вимкнена. Локально: IMAGE_GEN_URL=http://host.docker.internal:7860 "
            "і .\\scripts\\start_sd_forge.ps1"
        )
    if not prompt:
        return "Порожній опис для генерації."
    from .image_gen_lock import release, try_acquire

    if not await try_acquire():
        return (
            "Генерація зображень зараз зайнята (інший запит). "
            "Спробуй через хвилину — так Ollama не втрачає VRAM."
        )
    import base64

    backend = _image_gen_backend()
    try:
        img_bytes: bytes | None = None
        try:
            async with httpx.AsyncClient(timeout=settings.image_gen_timeout) as cli:
                if backend == "ollama":
                    img_bytes = await _generate_image_ollama(prompt)
                elif backend == "pollinations":
                    img_bytes = await _generate_image_pollinations(prompt)
                elif backend == "horde":
                    img_bytes = await _generate_image_horde(prompt)
                elif backend == "openai":
                    base = settings.image_gen_url.rstrip("/")
                    body: dict[str, Any] = {"prompt": prompt, "n": 1, "response_format": "b64_json"}
                    if settings.image_gen_model:
                        body["model"] = settings.image_gen_model
                    resp = await cli.post(f"{base}/images/generations", json=body)
                    resp.raise_for_status()
                    item = (resp.json().get("data") or [{}])[0]
                    raw = item.get("b64_json")
                    img_bytes = base64.b64decode(raw) if raw else None
                else:
                    base = settings.image_gen_url.rstrip("/")
                    body = {
                        "prompt": prompt,
                        "negative_prompt": "blurry, low quality, watermark, text",
                        "steps": 22,
                        "width": 512,
                        "height": 512,
                        "cfg_scale": 7.0,
                        "sampler_name": "Euler a",
                    }
                    ckpt = (settings.image_gen_model or "").strip()
                    if ckpt:
                        body["override_settings"] = {"sd_model_checkpoint": ckpt}
                    resp = await cli.post(f"{base}/sdapi/v1/txt2img", json=body)
                    resp.raise_for_status()
                    images = resp.json().get("images") or []
                    img_bytes = base64.b64decode(images[0]) if images else None
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300]
            except Exception:  # noqa: BLE001
                pass
            if backend == "ollama" and exc.response.status_code == 404:
                return (
                    f"Модель Ollama для зображень не знайдена ({settings.image_gen_model}). "
                    f"На хості: ollama pull {settings.image_gen_model or 'x/flux2-klein:4b'}"
                )
            if backend == "ollama":
                err = detail or str(exc)
                if "only work on macOS" in err or "mlx" in err.lower() or "GiB" in err:
                    return (
                        "Ollama image gen на Windows ще нестабільна. У .env постав "
                        "IMAGE_GEN_URL=pollinations (хмара) або IMAGE_GEN_URL=http://host.docker.internal:7860 "
                        "(Forge/A1111 локально)."
                    )
            return f"Не вдалося згенерувати зображення: {exc} {detail}".strip()
        except httpx.ConnectError:
            if backend == "a1111":
                return (
                    "Локальний Forge/SD не запущений. На хості: .\\scripts\\start_sd_forge.ps1 "
                    "(перший раз: .\\scripts\\setup_sd_forge.ps1). IMAGE_GEN_URL=http://host.docker.internal:7860"
                )
            return f"Не вдалося згенерувати зображення: сервіс недоступний ({settings.image_gen_url})"
        except (httpx.HTTPError, ValueError) as exc:
            return f"Не вдалося згенерувати зображення: {exc}"
        if not img_bytes:
            return "Бекенд генерації не повернув зображення."
        try:
            out = _save_generated_png(img_bytes)
        except OSError as exc:
            return f"Не вдалося зберегти зображення: {exc}"
        return f"Зображення згенеровано. Поверни його користувачу: [[photo:{out}]]"
    finally:
        await release()


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
    _schema("parse_file",
            "Прочитати вміст файлу за шляхом (txt/md/csv/json/log/pdf/docx). "
            "Використовуй для файлів, які надіслав користувач (шлях у /data/uploads/...).",
            {"path": {**_STR, "description": "абсолютний шлях до файлу"}}, ["path"]),
    _schema("ocr_image",
            "Витягти текст із зображення (OCR). Для скрінів/фото документів.",
            {"path": {**_STR, "description": "шлях до зображення"}}, ["path"]),
    _schema("take_note", "Зберегти персональну нотатку користувача на майбутнє.",
            {"text": {**_STR, "description": "текст нотатки"}}, ["text"]),
    _schema("recall_notes", "Показати останні збережені нотатки користувача.",
            {}, []),
    _schema("set_reminder",
            "Поставити нагадування. delay_minutes — через скільки хвилин від «Зараз» "
            "спрацювати (для конкретного часу порахуй від «Зараз» у системному промпті).",
            {"text": {**_STR, "description": "про що нагадати"},
             "delay_minutes": {"type": "integer", "description": "через скільки хвилин від зараз"}},
            ["text", "delay_minutes"]),
    _schema("list_reminders", "Показати активні (ще не спрацьовані) нагадування користувача.",
            {}, []),
    _schema(
        "cancel_reminder",
        "Скасувати нагадування за id (з list_reminders) або всі, якщо reminder_id='all'.",
        {"reminder_id": {**_STR, "description": "id нагадування або 'all'"}},
        ["reminder_id"],
    ),
    _schema(
        "show_in_app",
        "Показати багатий контент у Mini App (Канвас) — коли краще побачити, ніж читати "
        "текстом: графік/діаграма, таблиця, дашборд, мапа, відформатований звіт, зображення "
        "чи зовнішня сторінка. Для kind='html' можна вставляти <script> і CDN (напр. Chart.js) — "
        "це окрема пісочниця. Поряд із цим дай користувачу і короткий текстовий підсумок.",
        {
            "kind": {
                "type": "string",
                "enum": ["html", "markdown", "url", "image", "code"],
                "description": "тип контенту",
            },
            "content": {
                **_STR,
                "description": "HTML-розмітка / Markdown / http(s)-URL / посилання на зображення / код",
            },
            "title": {**_STR, "description": "короткий заголовок (необов'язково)"},
        },
        ["kind", "content"],
    ),
]

_CODE_SCHEMA = _schema(
    "code_exec", "Виконати короткий Python-скрипт і повернути stdout.",
    {"code": {**_STR, "description": "Python-код"}}, ["code"],
)

_COMPUTER_SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "run_powershell",
        "T0 PowerShell — найпряміший шлях на Windows. Спершу цей tier для OS-задач.",
        {
            "script": {**_STR, "description": "PowerShell-скрипт або команда"},
            "as_admin": {"type": "boolean", "description": "elevated (лише якщо дозволено)"},
        },
        ["script"],
    ),
    _schema(
        "run_cli",
        "T1 CLI — запуск exe без shell (git, winget, curl тощо).",
        {
            "exe": {**_STR, "description": "шлях або ім'я exe"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "аргументи"},
            "cwd": {**_STR, "description": "робоча директорія (необов'язково)"},
        },
        ["exe"],
    ),
    _schema(
        "fs_list",
        "T0 файли — список каталогу на хості (read-only).",
        {"path": {**_STR, "description": "абсолютний шлях до каталогу"}},
        ["path"],
    ),
    _schema(
        "fs_read",
        "T0 файли — прочитати файл на хості (read-only).",
        {"path": {**_STR, "description": "абсолютний шлях до файлу"}},
        ["path"],
    ),
    _schema(
        "fs_write",
        "T0 файли — записати текст у файл на хості (мутуюча дія).",
        {
            "path": {**_STR, "description": "абсолютний шлях до файлу"},
            "content": {**_STR, "description": "вміст для запису"},
        },
        ["path", "content"],
    ),
]

_SCREENSHOT_SCHEMA = _schema(
    "capture_screenshot",
    "Зняти скріншот основного екрана Windows і надіслати користувачу (read-only). "
    "Використовуй, коли просять «зроби скріншот», «покажи екран».",
    {},
    [],
)

_CLIPBOARD_READ_SCHEMA = _schema(
    "clipboard_read",
    "T0 — прочитати буфер обміну Windows (read-only).",
    {},
    [],
)

_CLIPBOARD_WRITE_SCHEMA = _schema(
    "clipboard_write",
    "T0 — записати текст у буфер обміну Windows (мутуюча дія).",
    {"text": {**_STR, "description": "текст для буфера"}},
    ["text"],
)

_SCREEN_CLICK_SCHEMA = _schema(
    "screen_click",
    "T4 — клік по координатах екрана (останній резерв, потребує confirm).",
    {"x": {"type": "integer", "description": "X"}, "y": {"type": "integer", "description": "Y"}},
    ["x", "y"],
)

_UIA_SCHEMAS: list[dict[str, Any]] = [
    _schema("window_list", "T3 — список вікон з заголовками на хості (read-only).", {}, []),
    _schema(
        "window_focus",
        "T3 — сфокусувати вікно за частиною заголовка.",
        {"title": {**_STR, "description": "частина заголовка вікна"}},
        ["title"],
    ),
    _schema(
        "uia_invoke",
        "T3 — UI Automation (фокус + Enter). control_name обов'язковий.",
        {
            "window": {**_STR, "description": "заголовок вікна (необов'язково)"},
            "control_name": {**_STR, "description": "ім'я контролу"},
            "action": {**_STR, "description": "click"},
        },
        ["control_name"],
    ),
]

_BROWSER_SCHEMAS: list[dict[str, Any]] = [
    _schema("browser_open", "T2 — відкрити URL у Playwright.", {"url": {**_STR, "description": "URL"}}, ["url"]),
    _schema("browser_read", "T2 — прочитати DOM/елементи поточної сторінки.", {}, []),
    _schema(
        "browser_click",
        "T2 — клік по CSS-селектору.",
        {"selector": {**_STR, "description": "CSS selector"}},
        ["selector"],
    ),
    _schema(
        "browser_fill",
        "T2 — заповнити input.",
        {"selector": {**_STR, "description": "CSS selector"}, "value": {**_STR, "description": "значення"}},
        ["selector", "value"],
    ),
    _schema(
        "browser_eval",
        "T2 — виконати JS на сторінці (read-only з точки зору confirm).",
        {"js": {**_STR, "description": "JavaScript вираз"}},
        ["js"],
    ),
]


_VISION_SCHEMA = _schema(
    "describe_image",
    "Описати зображення vision-моделлю (що на фото/скріні). Шлях — у /data/uploads/...",
    {"path": {**_STR, "description": "шлях до зображення"},
     "question": {**_STR, "description": "що саме спитати про зображення (необов'язково)"}},
    ["path"],
)

_IMAGEGEN_SCHEMA = _schema(
    "generate_image",
    "Згенерувати зображення за текстовим описом і повернути його користувачу.",
    {"prompt": {**_STR, "description": "опис бажаного зображення"}}, ["prompt"],
)


def agent_tool_schemas(*, computer: bool = False, allow_computer: bool = True) -> list[dict[str, Any]]:
    """Схеми, які віддаємо моделі. Опційні (vision/imagegen/code/computer) — за умовою."""
    schemas = list(TOOL_SCHEMAS)
    if settings.ollama_model_vision:
        schemas.append(_VISION_SCHEMA)
    if image_gen_enabled():
        schemas.append(_IMAGEGEN_SCHEMA)
    if settings.enable_code_exec:
        schemas.append(_CODE_SCHEMA)
    if settings.enable_computer_use and allow_computer:
        schemas.append(_SCREENSHOT_SCHEMA)
        if computer:
            schemas.extend(_COMPUTER_SCHEMAS)
            schemas.append(_CLIPBOARD_READ_SCHEMA)
            schemas.append(_CLIPBOARD_WRITE_SCHEMA)
            schemas.extend(_UIA_SCHEMAS)
            schemas.append(_SCREEN_CLICK_SCHEMA)
    if settings.enable_browser and computer:
        schemas.extend(_BROWSER_SCHEMAS)
    return schemas


_COMPUTER_TOOL_NAMES = frozenset(
    {
        "run_powershell",
        "run_cli",
        "fs_list",
        "fs_read",
        "fs_write",
        "capture_screenshot",
        "clipboard_read",
        "clipboard_write",
        "browser_open",
        "browser_read",
        "browser_click",
        "browser_fill",
        "browser_eval",
        "window_list",
        "window_focus",
        "uia_invoke",
        "screen_click",
    }
)


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    user_id: int = 0,
    *,
    allow_computer: bool = True,
) -> str:
    """Викликає інструмент за іменем. Помилки повертаються текстом (модель їх читає).

    user_id потрібен персональним інструментам (нотатки) — пробрасується з агент-лупа.
    """
    if name in _COMPUTER_TOOL_NAMES:
        from .computer_access import computer_denied_message

        denied = computer_denied_message(user_id)
        if denied or not allow_computer:
            return denied or (
                "Керування цим комп'ютером доступне лише власнику "
                "(COMPUTER_OWNER_USER_IDS у .env)."
            )
    t0 = time.perf_counter()
    try:
        if name == "calc":
            return calc(str(arguments.get("expression", "")))
        if name == "web_search":
            return await web_search(str(arguments.get("query", "")))
        if name == "web_fetch":
            return await web_fetch(str(arguments.get("url", "")))
        if name == "parse_file":
            return parse_file(str(arguments.get("path", "")))
        if name == "ocr_image":
            return await asyncio.to_thread(ocr_image, str(arguments.get("path", "")))
        if name == "describe_image":
            return await describe_image(
                str(arguments.get("path", "")), str(arguments.get("question", ""))
            )
        if name == "generate_image":
            return await generate_image(str(arguments.get("prompt", "")))
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
        if name == "set_reminder":
            from .reminders import add_reminder

            try:
                delay = int(arguments.get("delay_minutes", 0))
            except (TypeError, ValueError):
                delay = 0
            return await add_reminder(user_id, delay, str(arguments.get("text", "")))
        if name == "list_reminders":
            from .reminders import list_reminders

            return await list_reminders(user_id)
        if name == "cancel_reminder":
            from .reminders import cancel_all_reminders, cancel_reminder

            rid = str(arguments.get("reminder_id", "")).strip()
            if rid.lower() in ("all", "*"):
                return await cancel_all_reminders(user_id)
            return await cancel_reminder(user_id, rid)
        if name == "show_in_app":
            from .artifacts import show_in_app

            return await show_in_app(
                user_id,
                str(arguments.get("kind", "")),
                str(arguments.get("content", "")),
                str(arguments.get("title", "")),
            )
        if name == "run_powershell":
            from . import computer

            as_admin = bool(arguments.get("as_admin", False))
            return await computer.run_powershell(
                str(arguments.get("script", "")), as_admin, user_id=user_id
            )
        if name == "run_cli":
            from . import computer

            raw_args = arguments.get("args", [])
            args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
            cwd = str(arguments.get("cwd", "")) or None
            return await computer.run_cli(
                str(arguments.get("exe", "")), args, cwd, user_id=user_id
            )
        if name == "fs_list":
            from . import computer

            return await computer.fs_list(str(arguments.get("path", "")), user_id=user_id)
        if name == "fs_read":
            from . import computer

            return await computer.fs_read(str(arguments.get("path", "")), user_id=user_id)
        if name == "fs_write":
            from . import computer

            return await computer.fs_write(
                str(arguments.get("path", "")),
                str(arguments.get("content", "")),
                user_id=user_id,
            )
        if name == "capture_screenshot":
            from . import computer

            return await computer.capture_screenshot(user_id=user_id)
        if name == "clipboard_read":
            from . import computer

            return await computer.clipboard_read(user_id=user_id)
        if name == "clipboard_write":
            from . import computer

            return await computer.clipboard_write(str(arguments.get("text", "")), user_id=user_id)
        if name == "browser_open":
            from . import browser

            return await browser.browser_open(str(arguments.get("url", "")))
        if name == "browser_read":
            from . import browser

            return await browser.browser_read()
        if name == "browser_click":
            from . import browser
            from .computer_confirm import wrap_execute

            sel = str(arguments.get("selector", ""))
            return await wrap_execute(
                user_id,
                "browser_click",
                {"selector": sel},
                lambda: browser.browser_click(sel),
            )
        if name == "browser_fill":
            from . import browser
            from .computer_confirm import wrap_execute

            sel = str(arguments.get("selector", ""))
            val = str(arguments.get("value", ""))
            return await wrap_execute(
                user_id,
                "browser_fill",
                {"selector": sel, "value": val},
                lambda: browser.browser_fill(sel, val),
            )
        if name == "browser_eval":
            from . import browser

            js = str(arguments.get("js", ""))
            return await browser.browser_eval(js)
        if name == "window_list":
            from . import computer

            return await computer.window_list(user_id=user_id)
        if name == "window_focus":
            from . import computer

            return await computer.window_focus(
                str(arguments.get("title", "")), user_id=user_id
            )
        if name == "uia_invoke":
            from . import computer

            return await computer.uia_invoke(
                str(arguments.get("window", "")),
                str(arguments.get("control_name", "")),
                str(arguments.get("action", "click")),
                user_id=user_id,
            )
        if name == "screen_click":
            from . import computer

            try:
                x = int(arguments.get("x", 0))
                y = int(arguments.get("y", 0))
            except (TypeError, ValueError):
                return "invalid coordinates"
            return await computer.screen_click(x, y, user_id=user_id)
        if name == "schedule_job":
            from .jobs import schedule_job

            try:
                delay = int(arguments.get("delay_minutes", 0))
            except (TypeError, ValueError):
                delay = 0
            run_at = int(time.time()) + delay * 60
            jid = await schedule_job(
                user_id,
                run_at,
                str(arguments.get("macro", "")),
                str(arguments.get("note", "")),
            )
            return f"Job заплановано ({jid}) через {delay} хв."
        return f"Невідомий інструмент: {name}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s failed", name)
        return f"Інструмент {name} впав: {exc}"
    finally:
        from .metrics import record_tool

        await record_tool(name, (time.perf_counter() - t0) * 1000)


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
