"""CA-6.3 — code_edit_propose (IDE-міст): вміст+інструкція → unified diff, без apply."""
from __future__ import annotations

from app.agent import AgentRunner, _strip_code_fences


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, model, messages, tools=None):  # noqa: ANN001
        return {"content": self.content}


async def test_propose_returns_unified_diff() -> None:
    runner = AgentRunner(FakeLLM("y = 2\n"), object())
    out = await runner.code_edit_propose(1, path="m.py", instruction="bump", content="y = 1\n")
    assert out["changed"] is True
    assert out["proposed"] == "y = 2\n"
    assert "a/m.py" in out["diff"] and "b/m.py" in out["diff"]
    assert "-y = 1" in out["diff"] and "+y = 2" in out["diff"]


async def test_propose_strips_code_fences() -> None:
    runner = AgentRunner(FakeLLM("```python\ny = 2\n```"), object())
    out = await runner.code_edit_propose(1, path="m.py", instruction="bump", content="y = 1\n")
    assert out["proposed"] == "y = 2"  # огорожу прибрано (без trailing newline у цьому кейсі)


async def test_propose_no_change_empty_diff() -> None:
    runner = AgentRunner(FakeLLM("y = 1\n"), object())
    out = await runner.code_edit_propose(1, path="m.py", instruction="noop", content="y = 1\n")
    assert out["changed"] is False
    assert out["diff"] == ""


async def test_propose_requires_instruction() -> None:
    runner = AgentRunner(FakeLLM("whatever"), object())
    out = await runner.code_edit_propose(1, path="m.py", instruction="  ", content="x")
    assert out["changed"] is False and out.get("error") == "instruction required"


def test_strip_code_fences_plain_passthrough() -> None:
    assert _strip_code_fences("y = 1\n") == "y = 1\n"
    assert _strip_code_fences("```\na\nb\n```") == "a\nb"
