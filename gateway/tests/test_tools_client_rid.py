"""ToolsClient X-Request-ID headers."""
from app.tools_client import ToolsClient


def test_extra_headers_from_payload():
    h = ToolsClient._extra_headers({"request_id": "rid-1"})
    assert h == {"X-Request-ID": "rid-1"}


def test_extra_headers_empty():
    assert ToolsClient._extra_headers({}) == {}
