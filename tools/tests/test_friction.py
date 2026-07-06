"""Friction-телеметрія (SY-1): продюсери kind:friction — прапор, анти-leak, інтеграція."""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from app import context_emit, friction
from app.agent import AgentRunner
from app.config import settings

# Пакет toolkit ре-експортує ФУНКЦІЮ dispatch (перекриває підмодуль) — модуль беремо явно.
dmod = importlib.import_module("app.toolkit.dispatch")


class _IngestSpy:
    def __init__(self) -> None:
        self.stores: list[dict[str, Any]] = []

    async def context_ingest(self, store: dict[str, Any]) -> dict[str, Any]:
        self.stores.append(store)
        return {"inserted": True}


@pytest.fixture
def spy(monkeypatch):
    s = _IngestSpy()
    monkeypatch.setattr(context_emit, "_memory", s)
    monkeypatch.setattr(settings, "enable_friction_telemetry", True)
    return s


# --- модуль friction ---

async def test_flag_off_is_noop(monkeypatch):
    s = _IngestSpy()
    monkeypatch.setattr(context_emit, "_memory", s)
    monkeypatch.setattr(settings, "enable_friction_telemetry", False)
    friction.record_friction(7, friction.REASON_TOOL_FAIL, summary="x", tool="calc")
    await context_emit.drain()
    assert s.stores == []


async def test_record_builds_friction_passport(spy):
    friction.record_friction(
        7, friction.REASON_TOOL_FAIL, summary="Інструмент calc впав: ValueError", tool="calc"
    )
    await context_emit.drain()
    st = spy.stores[0]
    assert st["kind"] == "friction" and st["user_id"] == 7
    assert st["source"] == "agent_loop" and st["sensitivity"] == "personal"
    assert {"reason:tool_fail", "tool:calc", "module:tools"} <= set(st["tags"])


async def test_zero_user_is_skipped(spy):
    friction.record_friction(0, friction.REASON_TOOL_FAIL, summary="x", tool="calc")
    await context_emit.drain()
    assert spy.stores == []


async def test_summary_truncated(spy):
    friction.record_friction(7, friction.REASON_LOOP_EXHAUSTED, summary="д" * 500)
    await context_emit.drain()
    assert len(spy.stores[0]["summary"]) == 300


# --- інтеграція: dispatch (tool-fail / unknown-tool) ---

async def test_dispatch_tool_crash_emits_type_only(spy, monkeypatch):
    async def boom(args: dict[str, Any], uid: int) -> str:
        raise ValueError("секретний-шлях C:/Users/x/token=abc")

    monkeypatch.setitem(dmod._HANDLERS, "calc", boom)
    out = await dmod.dispatch("calc", {"expression": "2+2"}, user_id=7)
    await context_emit.drain()
    assert "впав" in out
    st = spy.stores[0]
    # Анти-leak: у паспорті лише ТИП помилки, ані шляхів, ані секретів.
    assert st["summary"] == "Інструмент calc впав: ValueError"
    assert "секретний" not in st["summary"] and "token" not in st["summary"]
    assert "reason:tool_fail" in st["tags"]


async def test_dispatch_unknown_tool_emits_friction(spy):
    out = await dmod.dispatch("neexistuje", {}, user_id=7)
    await context_emit.drain()
    assert "Невідомий інструмент" in out
    st = spy.stores[0]
    assert "reason:unknown_tool" in st["tags"] and "tool:neexistuje" in st["tags"]


# --- інтеграція: агент-луп (loop-exhausted) ---

class _FakeOllama:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    async def chat(self, model, messages, tools=None, num_predict=1024):
        return self._responses.pop(0)

    async def chat_stream(self, model, messages, num_predict=1024):
        yield "ok"


class _FakeMemory:
    async def search(self, user_id, query, top_k=5, project_id=None):
        return []

    async def store(self, user_id, content, role="user", project_id=None):
        return None

    async def history(self, user_id, limit=12):
        return []

    async def get_project(self, user_id, project_id):
        return None


async def test_loop_exhausted_emits_friction(spy, monkeypatch):
    monkeypatch.setattr(settings, "agent_mode", "agent")
    monkeypatch.setattr(settings, "max_agent_iters", 1)
    ollama = _FakeOllama(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "calc", "arguments": {"expression": "2+2"}}}],
            },
            {"role": "assistant", "content": "4"},  # примусовий фінал після need_final
        ]
    )
    out = await AgentRunner(ollama, _FakeMemory()).run(7, "скільки буде 2+2")
    await context_emit.drain()
    assert out["text"] == "4"
    reasons = {t for st in spy.stores for t in st["tags"]}
    assert "reason:loop_exhausted" in reasons
    exhausted = [st for st in spy.stores if "reason:loop_exhausted" in st["tags"]]
    assert "1 ітерацій" in exhausted[0]["summary"]
