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


# --- CA-4.1 code_plan: file-targets + kind=code -----------------------------

async def test_code_plan_stores_file_targets(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "summary": "Винести _helpers у jarvis_core",
        "steps": [
            {"file": "tools/app/x.py", "action": "видалити _helpers", "rationale": "дубль", "risk": "low"},
            {"file": "jarvis_core/h.py", "action": "додати _helpers", "rationale": "спільне", "risk": "medium"},
        ],
        "risks": ["імпорти"],
    }
    captured: dict = {}

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        captured["user_id"] = user_id
        from app.plans import _normalize_steps

        return {
            "id": "cp1",
            "user_id": user_id,
            "status": "pending",
            "kind": kwargs.get("kind", "general"),
            "steps": _normalize_steps(kwargs.get("steps", [])),
        }

    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    runner = AgentRunner(FakeLLM(json.dumps(payload)), object())
    result = await runner.code_plan(7, "винеси _helpers у jarvis_core")
    assert captured["kind"] == "code"
    assert "[[PLAN_CONFIRM:cp1]]" in result.get("marker", "")
    steps = result["steps"]
    assert steps[0]["file"] == "tools/app/x.py" and steps[0]["risk"] == "low"
    assert steps[1]["file"] == "jarvis_core/h.py" and steps[1]["action"] == "додати _helpers"


async def test_code_plan_fallback_on_bad_json(monkeypatch: pytest.MonkeyPatch):
    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        return {"id": "cp2", "user_id": user_id, "status": "pending", "steps": kwargs.get("steps", [])}

    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    runner = AgentRunner(FakeLLM("не JSON взагалі"), object())
    result = await runner.code_plan(7, "полагодь баг у auth.py")
    # фолбек — один крок із action із тексту
    assert result["steps"] and result["steps"][0]["action"] == "полагодь баг у auth.py"


def test_normalize_steps_preserves_code_fields():
    from app.plans import _normalize_steps

    out = _normalize_steps([{"file": "a.py", "action": "fix", "rationale": "bug", "risk": "HIGH"}])
    assert out[0]["file"] == "a.py" and out[0]["action"] == "fix"
    assert out[0]["rationale"] == "bug" and out[0]["risk"] == "high"  # нормалізовано lower


def test_normalize_steps_generic_has_no_code_fields():
    from app.plans import _normalize_steps

    out = _normalize_steps([{"title": "Build", "detail": "docker build"}])
    assert out[0]["title"] == "Build"
    assert "file" not in out[0] and "risk" not in out[0]  # generic-план не засмічений
