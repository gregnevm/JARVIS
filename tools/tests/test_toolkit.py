"""Інструменти агента: calc, coerce_args, парсери, схеми, dispatch, code_exec."""
from pathlib import Path

from app import toolkit
from app.config import settings


# --- calc ---
def test_calc_basic():
    assert toolkit.calc("2+2") == "4"


def test_calc_expression():
    assert toolkit.calc("17*23") == "391"


def test_calc_empty():
    assert toolkit.calc("   ") == "Порожній вираз."


def test_calc_too_long():
    assert toolkit.calc("1+" * 300 + "1") == "Завеликий вираз."


def test_calc_invalid_returns_error():
    assert toolkit.calc("2+").startswith("Помилка обчислення")


# --- coerce_args ---
def test_coerce_dict_passthrough():
    assert toolkit.coerce_args({"a": 1}) == {"a": 1}


def test_coerce_json_string():
    assert toolkit.coerce_args('{"x": 5}') == {"x": 5}


def test_coerce_non_dict_json():
    assert toolkit.coerce_args("[1,2]") == {}


def test_coerce_bad_json():
    assert toolkit.coerce_args("{not json}") == {}


def test_coerce_other_type():
    assert toolkit.coerce_args(123) == {}


# --- _html_to_text ---
def test_html_to_text_strips_tags_and_scripts():
    html = "<html><body><script>bad()</script><p>Привіт   світ</p></body></html>"
    out = toolkit._html_to_text(html)
    assert "bad()" not in out
    assert "Привіт світ" in out  # пробіли схлопнуто


# --- _parse_ddg ---
_DDG = """
<div class="result">
  <a class="result__a" href="https://a.example">Заголовок A</a>
  <a class="result__snippet">Опис A</a>
</div>
<div class="result">
  <a class="result__a" href="https://b.example">Заголовок B</a>
  <a class="result__snippet">Опис B</a>
</div>
<div class="result">
  <span>без посилання — пропускаємо</span>
</div>
"""


def test_parse_ddg_basic():
    items = toolkit._parse_ddg(_DDG, max_results=5)
    assert len(items) == 2  # третій блок без a.result__a пропущено
    assert items[0] == {"title": "Заголовок A", "url": "https://a.example", "snippet": "Опис A"}


def test_parse_ddg_respects_limit():
    assert len(toolkit._parse_ddg(_DDG, max_results=1)) == 1


# --- схеми інструментів ---
def test_schemas_default_excludes_code_exec(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", False)
    monkeypatch.setattr(settings, "enable_computer_use", False)
    monkeypatch.setattr(settings, "ollama_model_vision", "")
    monkeypatch.setattr(settings, "image_gen_url", "")
    monkeypatch.setattr(settings, "image_gen_model", "")
    monkeypatch.setattr(settings, "cursor_tasks_enabled", False)
    # Hermetic проти локального .env: ці гейти інакше підтягують реальні
    # MCP_SERVERS_JSON/NOTION_TOKEN/SLACK_BOT_TOKEN і додають mcp_call/конектори
    # у дефолтний набір (CI без .env проходить, dev-машина — ні).
    monkeypatch.setattr(settings, "mcp_servers_json", "")
    monkeypatch.setattr(settings, "notion_token", "")
    monkeypatch.setattr(settings, "slack_bot_token", "")
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas()]
    assert names == [
        "calc", "web_search", "web_fetch", "parse_file", "ocr_image", "take_note",
        "recall_notes", "set_reminder", "list_reminders", "cancel_reminder", "show_in_app",
        # calendar_upcoming — локальні reminders (не зовнішній connector API)
        "calendar_upcoming",
        "spawn_subagent",
    ]
    assert "code_exec" not in names


def test_schemas_include_code_exec_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas()]
    assert "code_exec" in names


# --- parse_file ---
def test_parse_file_missing():
    assert toolkit.parse_file("/no/such/file.txt").startswith("Файл не знайдено")


def test_parse_file_text(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("вміст файлу", encoding="utf-8")
    assert toolkit.parse_file(str(f)) == "вміст файлу"


def test_parse_file_unsupported(tmp_path: Path):
    f = tmp_path / "pic.xyz"
    f.write_text("x", encoding="utf-8")
    assert toolkit.parse_file(str(f)).startswith("Непідтримуваний формат")


# --- зображення (vision / OCR / генерація) ---
async def test_describe_image_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model_vision", "")
    assert (await toolkit.describe_image("/x.jpg")).startswith("Опис зображень вимкнено")


async def test_generate_image_disabled(monkeypatch):
    monkeypatch.setattr(settings, "image_gen_url", "")
    monkeypatch.setattr(settings, "image_gen_model", "")
    assert (await toolkit.generate_image("кіт")).startswith("Генерація зображень вимкнена")


async def test_generate_image_ollama(monkeypatch, tmp_path):
    async def _fake(prompt: str) -> bytes:
        assert prompt == "banana"
        return b"\x89PNG\r\n\x1a\n"

    async def _lock_acquire():
        return True

    async def _lock_release():
        return None

    monkeypatch.setattr(settings, "image_gen_url", "ollama")
    monkeypatch.setattr(settings, "image_gen_model", "x/z-image-turbo")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr("app.toolkit.image._generate_image_ollama", _fake)
    monkeypatch.setattr("app.image_gen_lock.try_acquire", _lock_acquire)
    monkeypatch.setattr("app.image_gen_lock.release", _lock_release)
    out = await toolkit.generate_image("banana")
    assert "[[photo:" in out
    assert (tmp_path / "uploads").exists()


def test_ocr_image_missing_file():
    assert toolkit.ocr_image("/no/such/img.png").startswith("Файл не знайдено")


def test_vision_imagegen_schemas_gated(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    monkeypatch.setattr(settings, "image_gen_url", "http://localhost:7860")
    monkeypatch.setattr(settings, "image_gen_model", "")
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas()]
    assert "describe_image" in names and "generate_image" in names


# --- dispatch ---
async def test_dispatch_calc():
    assert await toolkit.dispatch("calc", {"expression": "6*7"}) == "42"


async def test_dispatch_unknown_tool():
    assert (await toolkit.dispatch("nope", {})).startswith("Невідомий інструмент")


async def test_dispatch_calc_via_name():
    assert await toolkit.dispatch("calc", {"expression": "3*3"}) == "9"


# --- code_exec (sandbox: детально в test_toolkit_sandbox.py) ---
def test_code_exec_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", False)
    assert toolkit.code_exec("print(1)").startswith("Виконання коду вимкнено")


def test_code_exec_enabled_runs(monkeypatch):
    # legacy-режим (без bwrap): свідомий opt-out — суто щоб виконати реальний код у CI
    monkeypatch.setattr(settings, "enable_code_exec", True)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", False)
    monkeypatch.setattr("app.toolkit.sandbox.bwrap_path", lambda: None)
    assert toolkit.code_exec("print(2+2)") == "4"


def test_code_exec_fail_closed_without_sandbox(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", True)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", True)
    monkeypatch.setattr("app.toolkit.sandbox.bwrap_path", lambda: None)
    assert toolkit.code_exec("print(1)").startswith("Пісочниця недоступна")


def test_code_exec_guard_rejects_env_exfiltration(monkeypatch):
    # guard спрацьовує ДО спроби запуску — навіть без пісочниці
    monkeypatch.setattr(settings, "enable_code_exec", True)
    assert toolkit.code_exec("import os; print(os.environ)").startswith(
        "Код відхилено guard-правилом (deny:env-exfiltration)"
    )
