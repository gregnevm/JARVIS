"""CA-3.5 live-fix golden — fix_tests через СПРАВЖНІЙ run_tests-парсер.

На відміну від test_agent_fix_loop (run_tests замокано цілком), тут мокаємо лише
host-agent `/cli`, тож працює реальний pytest-парсер. «Правка» (stub _fix_round_edit)
фліпає симульований стан у green — замкнений цикл тест→правка→тест без LLM/мережі.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.agent import AgentRunner
from app.config import settings

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "fix_tests.json").read_text(encoding="utf-8")
)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.mark.parametrize("case", _GOLDEN, ids=lambda c: c["id"])
async def test_fix_tests_live_golden(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    monkeypatch.setattr("app.tools.fix_loop.get_redis", lambda: _FakeRedis())

    sim = {"fixed": bool(case["baseline_pass"])}

    async def _fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        assert path == "/cli"  # лише run_tests у цьому циклі (edit застабовано)
        if sim["fixed"]:
            return {"stdout": case["pass_stdout"], "stderr": "", "code": 0}
        return {"stdout": case["fail_stdout"], "stderr": "", "code": 1}

    monkeypatch.setattr("app.computer._request", _fake_request)

    async def _fake_edit_round(self, messages, tools, user_id):  # noqa: ANN001
        # «правка»: якщо сценарій передбачає виправлення — наступний прогон зелений
        if case["edit_fixes"]:
            sim["fixed"] = True

    monkeypatch.setattr(AgentRunner, "_fix_round_edit", _fake_edit_round)

    out = await AgentRunner(object(), object()).fix_tests(
        1, exe="pytest", max_rounds=case["max_rounds"]
    )
    assert out["status"] == case["expect_status"], out
    assert out["rounds"] == case["expect_rounds"]
    if case["expect_status"] in ("already_green", "fixed"):
        assert "✅ PASS" in out["report"]
