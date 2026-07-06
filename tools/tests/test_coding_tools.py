"""Native coding tools (Стовп B): repo_tree / repo_grep / code_read.

Усе мокаємо на рівні host-agent клієнта (`app.computer._request`) — без мережі.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app import toolkit
from app.config import settings
from app.tools import coding_tools


@pytest.fixture()
def coding_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr(settings, "coding_tree_max_entries", 300)
    monkeypatch.setattr(settings, "coding_grep_max_results", 60)


def _patch_request(return_value: dict[str, Any]) -> Any:
    return patch("app.computer._request", new_callable=AsyncMock, return_value=return_value)


# --- schema gating -----------------------------------------------------------

def test_schemas_hidden_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "repo_tree" not in names
    assert "repo_grep" not in names
    assert "code_read" not in names


def test_schemas_present_when_enabled(coding_enabled: None) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert {"repo_tree", "repo_grep", "code_read"} <= set(names)


def test_schemas_absent_outside_computer_mode(coding_enabled: None) -> None:
    # Не computer-режим → репо-інструменти не пропонуються (рідуть на host-agent).
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=False)]
    assert "repo_tree" not in names


# --- disabled / owner gating -------------------------------------------------

async def test_disabled_when_computer_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", False)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    out = await coding_tools.repo_tree(r"O:\JARVIS", user_id=1)
    assert "ENABLE_COMPUTER_USE" in out


async def test_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", False)
    out = await coding_tools.repo_grep("AgentRunner", path=".", user_id=1)
    assert "ENABLE_CODING_TOOLS" in out


async def test_dispatch_denies_non_owner(coding_enabled: None) -> None:
    out = await toolkit.dispatch("repo_tree", {"path": r"O:\JARVIS"}, user_id=99)
    assert "власник" in out.lower()


# --- repo_tree ---------------------------------------------------------------

async def test_repo_tree_builds_tree(coding_enabled: None) -> None:
    stdout = "app/main.py\napp/config.py\nREADME.md\n"
    with _patch_request({"stdout": stdout, "stderr": "", "code": 0}) as req:
        out = await coding_tools.repo_tree(r"O:\JARVIS", max_depth=3, user_id=1)
    # cwd=root, exe=rg, перший арг --files (далі — deny-глоби)
    args = req.await_args.kwargs["json"]
    assert args["exe"] == "rg" and args["args"][0] == "--files" and args["cwd"] == r"O:\JARVIS"
    assert "файлів: 3" in out
    assert "app/" in out
    assert "main.py" in out
    assert "README.md" in out


async def test_repo_tree_requires_path(coding_enabled: None) -> None:
    out = await coding_tools.repo_tree("", user_id=1)
    assert "path" in out.lower()


async def test_repo_tree_truncates(coding_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_tree_max_entries", 2)
    stdout = "\n".join(f"f{i}.py" for i in range(10))
    with _patch_request({"stdout": stdout, "code": 0}):
        out = await coding_tools.repo_tree(r"O:\repo", user_id=1)
    assert "показано 2 з 10" in out


# --- repo_grep ---------------------------------------------------------------

async def test_repo_grep_returns_matches(coding_enabled: None) -> None:
    stdout = "app/agent.py:42:class AgentRunner:\napp/agent.py:99:    runner = AgentRunner()\n"
    with _patch_request({"stdout": stdout, "stderr": "", "code": 0}) as req:
        out = await coding_tools.repo_grep("AgentRunner", path=r"O:\JARVIS", user_id=1)
    sent = req.await_args.kwargs["json"]["args"]
    assert "--" in sent and "AgentRunner" in sent
    assert sent[-1] == "AgentRunner"  # pattern після '--'
    assert "app/agent.py:42" in out


async def test_repo_grep_glob_filter(coding_enabled: None) -> None:
    with _patch_request({"stdout": "x.py:1:hit", "code": 0}) as req:
        await coding_tools.repo_grep("hit", glob="*.py", user_id=1)
    sent = req.await_args.kwargs["json"]["args"]
    assert "-g" in sent and "*.py" in sent


async def test_repo_grep_appends_secret_deny_after_user_glob(coding_enabled: None) -> None:
    # Захист від витоку: навіть якщо user передасть glob '.env', трейлінг '!.env'
    # (deny) має йти ПІСЛЯ нього (у ripgrep останній glob виграє).
    with _patch_request({"stdout": "", "code": 1}) as req:
        await coding_tools.repo_grep("KEY", glob=".env", user_id=1)
    sent = req.await_args.kwargs["json"]["args"]
    assert "!.env" in sent
    # user-glob '.env' має передувати deny '!.env'
    assert sent.index(".env") < sent.index("!.env")
    # і весь deny-блок — перед роздільником '--'
    assert sent.index("!.env") < sent.index("--")


async def test_repo_tree_excludes_secrets(coding_enabled: None) -> None:
    with _patch_request({"stdout": "app/main.py", "code": 0}) as req:
        await coding_tools.repo_tree(r"O:\repo", user_id=1)
    sent = req.await_args.kwargs["json"]["args"]
    assert sent[0] == "--files" and "!.env" in sent


async def test_repo_grep_no_matches(coding_enabled: None) -> None:
    with _patch_request({"stdout": "", "stderr": "", "code": 1}):
        out = await coding_tools.repo_grep("zzz_nope", path=".", user_id=1)
    assert "немає збігів" in out.lower()


async def test_repo_grep_requires_pattern(coding_enabled: None) -> None:
    out = await coding_tools.repo_grep("   ", user_id=1)
    assert "pattern" in out.lower()


async def test_repo_grep_caps_results(coding_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = "\n".join(f"f.py:{i}:hit" for i in range(20))
    with _patch_request({"stdout": rows, "code": 0}):
        out = await coding_tools.repo_grep("hit", max_results=5, user_id=1)
    assert "показано 5 з 20" in out
    # 5 рядків даних показано; 6-й рядок (f.py:5:hit) вже відсічено.
    assert "f.py:4:hit" in out and "f.py:5:hit" not in out


# --- code_read ---------------------------------------------------------------

async def test_code_read_line_range(coding_enabled: None) -> None:
    content = "\n".join(f"line{i}" for i in range(1, 11))
    with _patch_request({"path": "f.py", "content": content, "truncated": False}) as req:
        out = await coding_tools.code_read("f.py", start_line=3, end_line=5, user_id=1)
    assert req.await_args.kwargs["params"] == {"path": "f.py"}
    assert "рядки 3–5 з 10" in out
    assert "line3" in out and "line5" in out
    assert "line2" not in out and "line6" not in out


async def test_code_read_whole_file_default(coding_enabled: None) -> None:
    content = "a\nb\nc"
    with _patch_request({"path": "f.py", "content": content, "truncated": False}):
        out = await coding_tools.code_read("f.py", user_id=1)
    assert "рядки 1–3 з 3" in out


async def test_code_read_start_beyond_eof(coding_enabled: None) -> None:
    with _patch_request({"path": "f.py", "content": "a\nb", "truncated": False}):
        out = await coding_tools.code_read("f.py", start_line=50, user_id=1)
    assert "лише 2 рядків" in out


async def test_code_read_requires_path(coding_enabled: None) -> None:
    out = await coding_tools.code_read("", user_id=1)
    assert "path" in out.lower()


# --- repo_symbols ------------------------------------------------------------

_PY_SAMPLE = (
    "import os\n"
    "from typing import Any\n"
    "\n"
    "class Foo(Base):\n"
    "    def method(self, x: int) -> str:\n"
    "        return str(x)\n"
    "\n"
    "async def helper(a, b=1):\n"
    "    return a\n"
)


async def test_repo_symbols_python_ast(coding_enabled: None) -> None:
    with _patch_request({"path": "m.py", "content": _PY_SAMPLE}) as req:
        out = await coding_tools.repo_symbols("m.py", user_id=1)
    assert req.await_args.kwargs["params"] == {"path": "m.py"}
    assert "(ast," in out
    assert "class Foo(Base)" in out
    assert "def method(self, x: int) -> str" in out
    assert "async def helper(a, b=1)" in out
    assert "imports:" in out and "os" in out and "typing.Any" in out


async def test_repo_symbols_pattern_filter(coding_enabled: None) -> None:
    with _patch_request({"path": "m.py", "content": _PY_SAMPLE}):
        out = await coding_tools.repo_symbols("m.py", pattern="helper", user_id=1)
    assert "helper" in out and "method" not in out


async def test_repo_symbols_syntax_error(coding_enabled: None) -> None:
    with _patch_request({"path": "bad.py", "content": "def (:\n"}):
        out = await coding_tools.repo_symbols("bad.py", user_id=1)
    assert "розпарсити" in out.lower() or "syntax" in out.lower()


async def test_repo_symbols_regex_fallback_for_js(coding_enabled: None) -> None:
    js = "export function foo() {}\nclass Bar {}\nconst x = 1\n"
    with _patch_request({"path": "a.js", "content": js}):
        out = await coding_tools.repo_symbols("a.js", user_id=1)
    assert "(regex," in out
    assert "function foo" in out and "class Bar" in out
    assert "const x = 1" not in out  # не визначення


async def test_repo_symbols_requires_path(coding_enabled: None) -> None:
    out = await coding_tools.repo_symbols("", user_id=1)
    assert "path" in out.lower()


async def test_repo_symbols_in_schema(coding_enabled: None) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "repo_symbols" in names


# --- repo_refs (CA-4.5 foundation / CB3) -------------------------------------

_RG_REFS = (
    "tools/app/x.py:3:from tools.app.agent import AgentRunner\n"
    "tools/app/x.py:5:import tools.app.agent\n"
    "tools/app/y.py:10:    r = AgentRunner(llm, mem)\n"
    "tools/app/z.py:42:        self.runner = AgentRunner(a, b)\n"
)


async def test_repo_refs_classifies_imports_and_usages(coding_enabled: None) -> None:
    with _patch_request({"stdout": _RG_REFS, "stderr": "", "code": 0}) as req:
        out = await coding_tools.repo_refs("AgentRunner", path="O:/repo", user_id=1)
    # rg отримав -w і останній сегмент імені
    sent = req.await_args.kwargs["json"]
    assert sent["exe"] == "rg" and "-w" in sent["args"] and sent["args"][-1] == "AgentRunner"
    assert "import=2" in out and "usage=2" in out
    assert "import-сайти" in out and "usage-сайти" in out
    assert "from tools.app.agent import AgentRunner" in out
    assert "r = AgentRunner(llm, mem)" in out


async def test_repo_refs_dotted_module_uses_last_segment(coding_enabled: None) -> None:
    with _patch_request({"stdout": _RG_REFS, "stderr": "", "code": 0}) as req:
        await coding_tools.repo_refs("tools.app.agent", user_id=1)
    assert req.await_args.kwargs["json"]["args"][-1] == "agent"


async def test_repo_refs_rejects_bad_name(coding_enabled: None) -> None:
    out = await coding_tools.repo_refs("foo bar; rm -rf", user_id=1)
    assert "ідентифікатор" in out


async def test_repo_refs_no_matches(coding_enabled: None) -> None:
    with _patch_request({"stdout": "", "stderr": "", "code": 1}):
        out = await coding_tools.repo_refs("Nonexistent", user_id=1)
    assert "не знайдено" in out


async def test_repo_refs_in_schema(coding_enabled: None) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "repo_refs" in names


async def test_repo_refs_denied_for_non_owner(coding_enabled: None) -> None:
    out = await toolkit.dispatch("repo_refs", {"name": "AgentRunner"}, user_id=99)
    assert "власник" in out.lower()
