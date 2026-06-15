from jarvis_core.routing import RouteContext, classify_mode


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
