"""P3 agent.plan — mock LLM JSON."""
from __future__ import annotations

import json

import pytest

from app.agent import AgentRunner
from jarvis_core.llm.parsers import extract_json_object


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, model, messages, tools=None):  # noqa: ANN001
        return {"content": self.content}


async def test_extract_json_block():
    raw = '```json\n{"summary":"hi","steps":[],"risks":[]}\n```'
    data = extract_json_object(raw)
    assert data is not None
    assert data["summary"] == "hi"


async def test_plan_stores_record(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "summary": "Deploy app",
        "steps": [{"title": "Build", "detail": "docker build"}],
        "risks": ["downtime"],
    }
    llm = FakeLLM(json.dumps(payload))

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        return {
            "id": "plan1",
            "user_id": user_id,
            "status": "pending",
            "summary": kwargs.get("summary", ""),
            "steps": kwargs.get("steps", []),
        }

    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    runner = AgentRunner(llm, object())
    result = await runner.plan(42, "deploy my app")
    assert result["id"] == "plan1"
    assert "[[PLAN_CONFIRM:plan1]]" in result.get("marker", "")
