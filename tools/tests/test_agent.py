"""decide_mode + AgentRunner з підробленими Ollama/Memory (без мережі)."""
from typing import Any

import pytest

from app import agent
from app.agent import AgentRunner, decide_mode
from app.config import settings


# --- decide_mode ---
def test_mode_forced_chat():
    assert decide_mode("порахуй 2+2", "chat") == "chat"


def test_mode_forced_computer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    assert decide_mode("anything", "computer", user_id=1) == "computer"


def test_parse_confirm_marker():
    from app.agent import _parse_confirm

    got = _parse_confirm("[[COMPUTER_CONFIRM:deadbe]] Write file")
    assert got == {"code": "deadbe", "desc": "Write file"}


def test_hybrid_math_to_agent():
    assert decide_mode("скільки буде 2+2", "hybrid") == "agent"


def test_hybrid_url_to_agent():
    assert decide_mode("відкрий http://example.com", "hybrid") == "agent"


def test_hybrid_keyword_to_agent():
    assert decide_mode("знайди погоду в Києві", "hybrid") == "agent"


def test_hybrid_plain_to_chat():
    assert decide_mode("розкажи жарт", "hybrid") == "chat"


def test_hybrid_file_attachment_to_agent():
    assert decide_mode("Користувач надіслав файл. parse_file зі шляхом /data/x.pdf", "hybrid") == "agent"


def test_hybrid_image_gen_to_agent():
    assert decide_mode("намалюй щеня", "hybrid") == "agent"


def test_hybrid_note_to_agent():
    assert decide_mode("запиши нотатку: купити хліб", "hybrid") == "agent"
    assert decide_mode("покажи мої нотатки", "hybrid") == "agent"


def _enable_computer_for_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "admin_user_ids", "1")


def test_decide_mode_screenshot_routes_computer_when_computer_enabled(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("зроби скріншот", "hybrid", user_id=1) == "computer"
    assert decide_mode("take a screenshot please", "hybrid", user_id=1) == "computer"
    assert decide_mode("зроби скріншот", "chat", user_id=1) == "chat"
    assert decide_mode("зроби скріншот", "hybrid", user_id=2) == "chat"


def test_decide_mode_computer_keywords_hybrid(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("запусти winget install vlc", "hybrid", user_id=1) == "computer"
    assert decide_mode("прочитай файл C:\\Users\\test\\a.txt", "hybrid", user_id=1) == "computer"
    assert decide_mode("docker ps на хості", "hybrid", user_id=1) == "computer"


def test_decide_mode_note_stays_agent_not_computer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", True)
    assert decide_mode("запиши нотатку: купити хліб", "hybrid") == "agent"


def test_decide_mode_hint_forces_computer_for_owner(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("жарт", "hybrid", mode_hint="computer", user_id=1) == "computer"
    assert decide_mode("жарт", "hybrid", mode_hint="computer", user_id=2) == "agent"


def test_decide_mode_screen_region_without_kw_still_computer_when_computer_on(
    monkeypatch: pytest.MonkeyPatch,
):
    """_COMPUTER_RE ловить «скрін екран»."""
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("зроби скрін екран зараз", "hybrid", user_id=1) == "computer"


def test_decide_mode_what_on_screen_routes_computer(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("що на екрані зараз?", "hybrid", user_id=1) == "computer"


def test_decide_mode_cursor_prefix_routes_computer(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("cursor: додай тести", "hybrid", user_id=1) == "computer"


def test_decide_mode_open_excel_routes_computer(monkeypatch: pytest.MonkeyPatch):
    _enable_computer_for_owner(monkeypatch)
    assert decide_mode("відкрий excel", "hybrid", user_id=1) == "computer"


# --- фейки ---
class FakeOllama:
    def __init__(
        self,
        responses: list[dict[str, Any]],
        stream_tokens: list[str] | None = None,
    ) -> None:
        self._responses = list(responses)
        self._stream_tokens = list(stream_tokens or [])
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model, messages, tools=None, num_predict=1024):
        self.calls.append({"model": model, "tools": tools})
        return self._responses.pop(0)

    async def chat_stream(self, model, messages, num_predict=1024):
        for tok in self._stream_tokens:
            yield tok


class FakeMemory:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.stored: list[tuple[str, str]] = []

    async def search(self, user_id, query, top_k=5, project_id=None):
        return self.results

    async def store(self, user_id, content, role="user", project_id=None):
        self.stored.append((role, content))

    async def history(self, user_id, limit=12):
        return []

    async def get_project(self, user_id, project_id):
        return None


async def test_run_chat_mode(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "chat")
    ollama = FakeOllama([{"role": "assistant", "content": "Привіт!"}])
    mem = FakeMemory()
    out = await AgentRunner(ollama, mem).run(1, "привіт")
    assert out == {"text": "Привіт!", "mode": "chat", "iters": 0}
    assert mem.stored == [("user", "привіт"), ("assistant", "Привіт!")]
    assert ollama.calls[0]["tools"] is None  # у чаті інструменти не передаємо


async def test_run_agent_mode_tool_loop(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "agent")
    ollama = FakeOllama(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "calc", "arguments": {"expression": "2+2"}}}],
            },
            {"role": "assistant", "content": "Відповідь: 4"},
        ]
    )
    mem = FakeMemory()
    out = await AgentRunner(ollama, mem).run(1, "скільки буде 2+2")
    assert out["text"] == "Відповідь: 4"
    assert out["mode"] == "agent"
    assert out["iters"] == 2  # 1 ітерація з тулом + 1 з фінальним текстом
    assert ollama.calls[0]["tools"] is not None  # інструменти передані моделі


async def test_run_stream_chat_mode(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "chat")
    ollama = FakeOllama([], stream_tokens=["При", "віт", "!"])
    mem = FakeMemory()
    events = [ev async for ev in AgentRunner(ollama, mem).run_stream(1, "привіт")]
    deltas = "".join(e["delta"] for e in events if "delta" in e)
    assert deltas == "Привіт!"
    done = events[-1]
    assert done["done"] is True and done["mode"] == "chat" and done["text"] == "Привіт!"
    assert mem.stored == [("user", "привіт"), ("assistant", "Привіт!")]


async def test_run_stream_agent_mode_status_and_answer(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "agent")
    ollama = FakeOllama(
        [
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "calc", "arguments": {"expression": "2+2"}}}]},
            {"role": "assistant", "content": "Відповідь: 4"},
        ]
    )
    mem = FakeMemory()
    events = [ev async for ev in AgentRunner(ollama, mem).run_stream(1, "скільки буде 2+2")]
    statuses = [e["status"] for e in events if "status" in e]
    assert any("рахую" in s for s in statuses)  # статус-мітка інструмента calc
    done = events[-1]
    assert done["done"] is True and done["mode"] == "agent"
    assert done["text"] == "Відповідь: 4" and done["iters"] == 2
    assert ("assistant", "Відповідь: 4") in mem.stored


async def test_run_fallback_on_empty_answer(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "chat")
    ollama = FakeOllama([{"role": "assistant", "content": "   "}])
    mem = FakeMemory()
    out = await AgentRunner(ollama, mem).run(1, "щось")
    assert out["text"] == agent.FALLBACK
    assert mem.stored == [("user", "щось")]  # порожню відповідь не зберігаємо


# --- inline tool-call фолбек (qwen2.5 інколи віддає виклик текстом) ---
def test_parse_inline_no_args():
    content = 'ось виклик\n<tool_call>\n{"name": "recall_notes", "arguments": {}}\n</tool_call>'
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "recall_notes"
    assert calls[0]["function"]["arguments"] == {}


def test_parse_inline_with_args():
    calls = agent._parse_inline_tool_calls('{"name": "calc", "arguments": {"expression": "2+2"}}')
    assert calls[0]["function"]["name"] == "calc"
    assert calls[0]["function"]["arguments"] == {"expression": "2+2"}


def test_parse_inline_none():
    assert agent._parse_inline_tool_calls("звичайний текст без викликів") == []


def test_parse_inline_nested_object_args():
    """Вкладений arguments-об'єкт (mcp_call) має зберегтись повністю, не зрізатись до {}."""
    content = '{"name": "mcp_call", "arguments": {"server": "s", "tool": "t", "arguments": {"q": "hi"}}}'
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "mcp_call"
    assert calls[0]["function"]["arguments"] == {
        "server": "s",
        "tool": "t",
        "arguments": {"q": "hi"},
    }


def test_parse_inline_list_and_nested_args():
    """arguments зі списком об'єктів (code_edit_batch) парситься без втрати."""
    content = (
        '<tool_call>{"name": "code_edit_batch", "arguments": '
        '{"edits": [{"path": "a.py", "new": "x"}, {"path": "b.py", "new": "y"}]}}</tool_call>'
    )
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["arguments"]["edits"][1] == {"path": "b.py", "new": "y"}


def test_parse_inline_braces_in_string_value():
    """Дужки всередині рядкового значення не ламають баланс."""
    content = '{"name": "fs_write", "arguments": {"path": "a", "content": "a {b} c}"}}'
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["arguments"] == {"path": "a", "content": "a {b} c}"}


def test_parse_inline_multiple_calls_one_nested():
    """Кілька викликів підряд, один із вкладеним об'єктом — обидва зчитані коректно."""
    content = (
        '{"name": "calc", "arguments": {"expression": "2+2"}} і ще '
        '{"name": "mcp_call", "arguments": {"tool": "t", "arguments": {"q": "x"}}}'
    )
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 2
    assert calls[0]["function"]["arguments"] == {"expression": "2+2"}
    assert calls[1]["function"]["arguments"] == {"tool": "t", "arguments": {"q": "x"}}


def test_parse_inline_unterminated_object_emits_name_with_empty_args():
    """Стрім обірвано посеред виклику: scanner → None, але ім'я емітимо, args={}, без зависання."""
    content = '<tool_call>{"name": "mcp_call", "arguments": {"server": "s", "tool": "t"'
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "mcp_call"
    assert calls[0]["function"]["arguments"] == {}


def test_parse_inline_balanced_but_invalid_json():
    """Збалансовані дужки, але невалідний JSON (trailing comma) → name є, args={}, без винятку."""
    content = '{"name": "x", "arguments": {"a": 1,}}'
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "x"
    assert calls[0]["function"]["arguments"] == {}


def test_parse_inline_deeply_nested_args_no_raise():
    """json.loads кидає RecursionError на глибокій вкладеності — фолбек не падає, args={}."""
    inner = "1"
    for _ in range(2000):
        inner = '{"a":' + inner + "}"
    content = '{"name": "mcp_call", "arguments": ' + inner + "}"
    calls = agent._parse_inline_tool_calls(content)  # не має кидати
    assert calls[0]["function"]["name"] == "mcp_call"
    assert calls[0]["function"]["arguments"] == {}


def test_parse_inline_many_unbalanced_stays_linear():
    """Повторювані обрізані відкриття не дають O(n²): break зупиняє ре-сканування до EOF."""
    content = '{"name":"x","arguments":{' * 20000  # ~0.5 MB, усі незакриті
    import time as _t

    t0 = _t.perf_counter()
    calls = agent._parse_inline_tool_calls(content)
    elapsed = _t.perf_counter() - t0
    assert elapsed < 1.0  # лінійно (без break — десятки секунд); великий запас на CI-шум
    assert len(calls) == 1  # перше відкриття незбалансоване → один виклик, потім break
    assert calls[0]["function"]["arguments"] == {}


def test_parse_inline_multiline_pretty_nested():
    """Pretty-printed (багаторядковий) вкладений arguments має пережити зняття re.DOTALL."""
    content = (
        "<tool_call>\n{\n"
        '  "name": "mcp_call",\n'
        '  "arguments": {\n'
        '    "server": "s",\n'
        '    "arguments": {\n'
        '      "q": "hi"\n'
        "    }\n  }\n}\n</tool_call>"
    )
    calls = agent._parse_inline_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["arguments"] == {"server": "s", "arguments": {"q": "hi"}}


async def test_run_agent_handles_inline_tool_call(monkeypatch):
    """Модель віддала tool call текстом → loop має його виконати, а не злити юзеру."""
    monkeypatch.setattr(settings, "agent_mode", "agent")
    ollama = FakeOllama(
        [
            {"role": "assistant",
             "content": '<tool_call>{"name": "calc", "arguments": {"expression": "2+2"}}</tool_call>'},
            {"role": "assistant", "content": "Відповідь: 4"},
        ]
    )
    out = await AgentRunner(ollama, FakeMemory()).run(1, "скільки буде 2+2")
    assert out["text"] == "Відповідь: 4"
    assert out["iters"] == 2  # inline-виклик оброблено як справжній
