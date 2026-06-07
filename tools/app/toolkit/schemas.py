"""OpenAI function schemas for agent tools."""
from __future__ import annotations

from typing import Any

from ..config import settings
from .image import image_gen_enabled

_STR = {"type": "string"}


def _schema(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


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

_SUBAGENT_SCHEMA = _schema(
    "spawn_subagent",
    "Делегувати підзадачу суб-агенту з обмеженим budget_iters (1–8 tool loops).",
    {
        "task": {**_STR, "description": "опис підзадачі"},
        "budget_iters": {"type": "integer", "description": "макс. ітерацій тул-лупа (default 3)"},
    },
    ["task"],
)

_CURSOR_TASK_SCHEMA = _schema(
    "cursor_task",
    "Поставити coding-задачу Cursor IDE agent (локально на O:\\JARVIS або cloud). "
    "Краще за довгі PowerShell-скрипти для змін у коді.",
    {
        "task": {**_STR, "description": "повний опис задачі для Cursor"},
        "async_mode": {
            "type": "boolean",
            "description": "true = фонова черга + результат пізніше (default true)",
        },
    },
    ["task"],
)

_MCP_CALL_SCHEMA = _schema(
    "mcp_call",
    "Виклик інструменту зовнішнього MCP-сервера (allowlist у .env).",
    {
        "server": {**_STR, "description": "ім'я MCP server з конфігу"},
        "tool": {**_STR, "description": "ім'я tool на сервері"},
        "arguments": {"type": "object", "description": "аргументи tool"},
    },
    ["server", "tool"],
)


def _mcp_enabled() -> bool:
    return bool((settings.mcp_servers_json or "").strip())


def _connector_schemas() -> list[dict[str, Any]]:
    from ..connectors import calendar, notion, slack

    out: list[dict[str, Any]] = []
    if notion.is_configured():
        out.extend([
            _schema("notion_search", "Пошук сторінок у Notion.", {"query": {**_STR}}, ["query"]),
            _schema(
                "notion_read_page",
                "Прочитати сторінку Notion за id.",
                {"page_id": {**_STR}},
                ["page_id"],
            ),
        ])
    if slack.is_configured():
        out.extend([
            _schema(
                "slack_post_message",
                "Надіслати повідомлення в Slack.",
                {
                    "text": {**_STR},
                    "channel": {**_STR, "description": "канал (необов'язково)"},
                },
                ["text"],
            ),
            _schema("slack_list_channels", "Список Slack каналів.", {}, []),
        ])
    out.append(
        _schema(
            "calendar_upcoming",
            "Найближчі нагадування та події (reminders + опційно ICS).",
            {"days": {"type": "integer", "description": "горизонт днів"}},
            [],
        )
    )
    return out


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
            if settings.cursor_tasks_enabled:
                schemas.append(_CURSOR_TASK_SCHEMA)
            schemas.extend(_COMPUTER_SCHEMAS)
            schemas.append(_CLIPBOARD_READ_SCHEMA)
            schemas.append(_CLIPBOARD_WRITE_SCHEMA)
            schemas.extend(_UIA_SCHEMAS)
            schemas.append(_SCREEN_CLICK_SCHEMA)
    if settings.enable_browser and computer:
        schemas.extend(_BROWSER_SCHEMAS)
    schemas.extend(_connector_schemas())
    if _mcp_enabled():
        schemas.append(_MCP_CALL_SCHEMA)
    schemas.append(_SUBAGENT_SCHEMA)
    if settings.cursor_tasks_enabled and not computer:
        schemas.append(_CURSOR_TASK_SCHEMA)
    return schemas


COMPUTER_TOOL_NAMES = frozenset(
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
