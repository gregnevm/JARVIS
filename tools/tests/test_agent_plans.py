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


async def test_code_plan_stores_file_targeted_steps(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "summary": "Extract helpers",
        "steps": [
            {"file": "jarvis_core/util.py", "action": "add helper", "rationale": "reuse", "risk": "low"},
            {"file": "tools/app/agent.py", "action": "import helper", "rationale": "dedupe", "risk": "medium"},
        ],
        "risks": ["import cycles"],
    }
    llm = FakeLLM(json.dumps(payload))
    captured: dict[str, object] = {}

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return {"id": "cp1", "user_id": user_id, "status": "pending",
                "summary": kwargs.get("summary", ""), "steps": kwargs.get("steps", [])}

    monkeypatch.setattr("app.computer_trust.trust_level", _trust(None))
    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    runner = AgentRunner(llm, object())
    result = await runner.code_plan(7, "extract helpers into jarvis_core")
    assert result["id"] == "cp1" and result["kind"] == "code"
    assert "[[PLAN_CONFIRM:cp1]]" in result.get("marker", "")
    assert result["auto_approved"] is False and captured["status"] == "pending"
    # file-targets дійшли до create_plan
    steps = captured["steps"]
    assert steps[0]["file"] == "jarvis_core/util.py" and steps[1]["file"] == "tools/app/agent.py"


def _trust(level):  # noqa: ANN001
    async def _fn(user_id):  # noqa: ANN001
        return level
    return _fn


# --- CA-4.2 session-trust auto-approve --------------------------------------

async def test_code_plan_auto_approves_within_session_trust(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return {"id": "cp2", "user_id": user_id, "status": kwargs.get("status"), "steps": []}

    monkeypatch.setattr("app.computer_trust.trust_level", _trust("session"))
    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    llm = FakeLLM('{"summary":"s","steps":[{"file":"a.py","action":"x"}],"risks":[]}')
    result = await AgentRunner(llm, object()).code_plan(7, "fix a.py")
    assert captured["status"] == "approved"  # авто-апрув у вікні trust
    assert result["auto_approved"] is True
    assert result.get("marker", "") == ""  # без confirm-маркера


async def test_code_plan_pending_without_trust(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return {"id": "cp3", "user_id": user_id, "status": kwargs.get("status"), "steps": []}

    monkeypatch.setattr("app.computer_trust.trust_level", _trust(None))
    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    llm = FakeLLM('{"summary":"s","steps":[{"file":"a.py","action":"x"}],"risks":[]}')
    result = await AgentRunner(llm, object()).code_plan(7, "fix a.py")
    assert captured["status"] == "pending"
    assert result["auto_approved"] is False
    assert "[[PLAN_CONFIRM:cp3]]" in result["marker"]


async def test_code_plan_bypass_auto_approves_without_trust(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    captured: dict[str, object] = {}

    async def _fake_create(user_id, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return {"id": "cp4", "user_id": user_id, "status": kwargs.get("status"), "steps": []}

    monkeypatch.setattr(settings, "bypass_confirmations", True)
    monkeypatch.setattr("app.computer_trust.trust_level", _trust(None))  # навіть без trust
    monkeypatch.setattr("app.plans.create_plan", _fake_create)
    llm = FakeLLM('{"summary":"s","steps":[{"file":"a.py","action":"x"}],"risks":[]}')
    result = await AgentRunner(llm, object()).code_plan(7, "fix a.py")
    assert captured["status"] == "approved"  # глобальний bypass → авто-апрув
    assert result["auto_approved"] is True and result.get("marker", "") == ""


def test_normalize_steps_preserves_code_fields():
    from app.plans import _normalize_steps

    out = _normalize_steps(
        [{"file": "a.py", "action": "edit", "rationale": "why", "risk": "high"}]
    )
    assert out[0]["file"] == "a.py" and out[0]["action"] == "edit"
    assert out[0]["risk"] == "high" and out[0]["title"] == "edit"


def test_normalize_steps_plain_string_has_no_code_fields():
    from app.plans import _normalize_steps

    out = _normalize_steps(["just do it"])
    assert "file" not in out[0] and out[0]["title"] == "just do it"
