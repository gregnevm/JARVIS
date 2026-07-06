"""P4 deep research orchestrator."""
import pytest
from app import research


async def test_deep_research_empty():
    out = await research.deep_research("")
    assert "Порожній" in out["report"]


async def test_deep_research_mock_search(monkeypatch: pytest.MonkeyPatch):
    async def _search(query, max_results=5):
        return "1. Example\n   snippet\n   https://example.com/page"

    async def _fetch(url):
        return f"Content from {url}"

    monkeypatch.setattr(research, "web_search", _search)
    monkeypatch.setattr(research, "web_fetch", _fetch)
    out = await research.deep_research("test topic", max_hops=1)
    assert out["sources"]
    assert "[1]" in out["report"] or "example.com" in out["report"]
