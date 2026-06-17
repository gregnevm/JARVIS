from jarvis_core.routing import RouteContext, classify_mode, is_screenshot_request


def test_forced_hint():
    ctx = RouteContext(mode_hint="agent")
    assert classify_mode("anything", ctx) == "agent"


def test_computer_gated():
    ctx = RouteContext(
        mode_hint="computer", enable_computer=True, computer_allowed=False
    )
    assert classify_mode("x", ctx) == "agent"


def test_hybrid_computer_heuristic():
    ctx = RouteContext(agent_mode="hybrid", enable_computer=True, computer_allowed=True)
    assert classify_mode("зроби скріншот", ctx) == "computer"


def test_hybrid_agent_url():
    ctx = RouteContext(agent_mode="hybrid")
    assert classify_mode("відкрий https://example.com", ctx) == "agent"


def test_hybrid_chat():
    ctx = RouteContext(agent_mode="hybrid")
    assert classify_mode("привіт", ctx) == "chat"


def test_hybrid_computer_what_on_screen():
    ctx = RouteContext(agent_mode="hybrid", enable_computer=True, computer_allowed=True)
    assert classify_mode("що на екрані?", ctx) == "computer"


def test_hybrid_computer_cursor_prefix():
    ctx = RouteContext(agent_mode="hybrid", enable_computer=True, computer_allowed=True)
    assert classify_mode("cursor: fix tests", ctx) == "computer"


# R4 — screenshot-shortcut патерн (перенесено з gateway-транспорту в routing)
def test_is_screenshot_request_matches() -> None:
    assert is_screenshot_request("зроби скріншот")
    assert is_screenshot_request("take a screenshot please")
    assert is_screenshot_request("скрін екран зараз")


def test_is_screenshot_request_negatives() -> None:
    assert not is_screenshot_request("розкажи жарт")
    assert not is_screenshot_request("")
