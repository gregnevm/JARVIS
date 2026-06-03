"""decide_mode + AgentRunner з підробленими Ollama/Memory (без мережі)."""
from typing import Any

from app import agent
from app.agent import AgentRunner, decide_mode
from app.config import settings


# --- decide_mode ---
def test_mode_forced_chat():
    assert decide_mode("порахуй 2+2", "chat") == "chat"


def test_mode_forced_agent():
    assert decide_mode("просто привіт", "agent") == "agent"


def test_hybrid_math_to_agent():
    assert decide_mode("скільки буде 2+2", "hybrid") == "agent"


def test_hybrid_url_to_agent():
    assert decide_mode("відкрий http://example.com", "hybrid") == "agent"


def test_hybrid_keyword_to_agent():
    assert decide_mode("знайди погоду в Києві", "hybrid") == "agent"


def test_hybrid_plain_to_chat():
    assert decide_mode("розкажи жарт", "hybrid") == "chat"


# --- фейки ---
class FakeOllama:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model, messages, tools=None, num_predict=1024):
        self.calls.append({"model": model, "tools": tools})
        return self._responses.pop(0)


class FakeMemory:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.stored: list[tuple[str, str]] = []

    async def search(self, user_id, query, top_k=5):
        return self.results

    async def store(self, user_id, content, role="user"):
        self.stored.append((role, content))


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


async def test_run_fallback_on_empty_answer(monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "chat")
    ollama = FakeOllama([{"role": "assistant", "content": "   "}])
    mem = FakeMemory()
    out = await AgentRunner(ollama, mem).run(1, "щось")
    assert out["text"] == agent.FALLBACK
    assert mem.stored == [("user", "щось")]  # порожню відповідь не зберігаємо
