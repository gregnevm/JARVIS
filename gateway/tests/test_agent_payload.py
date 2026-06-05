"""agent_payload builder."""
from app.agent_payload import build_agent_payload
from app.request_id import set_request_id


def test_build_includes_request_id():
    set_request_id("abc123")
    p = build_agent_payload(user_id=1, chat_id=2, text="hi", mode="agent")
    assert p["request_id"] == "abc123"
    assert p["user_id"] == 1
    assert p["mode"] == "agent"


def test_build_without_rid():
    set_request_id("")
    p = build_agent_payload(user_id=1, chat_id=2, text="hi")
    assert "request_id" not in p
