"""Golden traces — регресія routing, safety, tool dispatch (Фаза 5.1)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from jarvis_core.pipeline.handlers import screen_text
from jarvis_core.routing import RouteContext, classify_mode

_GOLDEN = Path(__file__).parent / "golden"


def _load(name: str) -> list[dict]:
    return json.loads((_GOLDEN / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load("routing.json"), ids=lambda c: c.get("id", c["text"][:20] or "empty"))
def test_golden_routing(case: dict):
    ctx = RouteContext(
        agent_mode=case.get("agent_mode", "hybrid"),
        mode_hint=case.get("mode_hint"),
        enable_computer=case.get("enable_computer", False),
        computer_allowed=case.get("computer_allowed", True),
    )
    assert classify_mode(case["text"], ctx) == case["expected"]


@pytest.mark.parametrize("case", _load("safety.json"), ids=lambda c: c["text"][:20])
def test_golden_safety(case: dict):
    safe, block = screen_text(case["text"])
    if case.get("blocked"):
        assert block is not None
    else:
        assert block is None
        assert safe == case.get("safe", case["text"].strip())


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load("tool_dispatch.json"), ids=lambda c: c["tool"])
async def test_golden_tool_dispatch(case: dict, monkeypatch: pytest.MonkeyPatch):
    from app import toolkit
    from app.config import settings

    if case.get("enable_browser"):
        monkeypatch.setattr(settings, "enable_browser", True)
    if case["tool"] == "calc":
        out = await toolkit.dispatch(case["tool"], case["args"], user_id=1)
    elif case["tool"] == "browser_open":
        from app import browser

        monkeypatch.setattr(settings, "enable_browser", case.get("enable_browser", True))
        out = await browser.browser_open(str(case["args"].get("url", "")))
    else:
        pytest.skip(f"no handler for {case['tool']}")
    assert case["expect_substr"] in out
