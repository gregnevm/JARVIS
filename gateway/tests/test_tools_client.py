"""ToolsClient — POST /agent через httpx MockTransport."""
import asyncio

import httpx

from app.tools_client import ToolsClient, extract_text


def test_process_returns_agent_text():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agent"
        assert req.method == "POST"
        return httpx.Response(200, json={"text": "відповідь", "mode": "chat"})

    async def _run() -> str:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as raw:
            client = ToolsClient("http://tools:8200", timeout=5.0)
            client._client = raw
            return await client.process({"user_id": 1, "text": "привіт"})

    assert asyncio.run(_run()) == "відповідь"


def test_process_missing_fields_fallback():
    async def _run() -> str:
        client = ToolsClient("http://tools:8200")
        try:
            return await client.process({})
        finally:
            await client.aclose()

    assert asyncio.run(_run()) != ""


def test_extract_text_tools_shape():
    assert extract_text({"text": "ok"}) == "ok"
