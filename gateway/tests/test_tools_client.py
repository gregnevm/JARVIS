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


def test_stream_yields_parsed_events():
    body = (
        b'{"delta":"\\u041f\\u0440\\u0438"}\n'
        b'{"delta":"\\u0432\\u0456\\u0442"}\n'
        b'{"done":true,"text":"\\u041f\\u0440\\u0438\\u0432\\u0456\\u0442","mode":"chat","iters":0}\n'
    )

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agent/stream"
        return httpx.Response(200, content=body)

    async def _run() -> list[dict]:
        client = ToolsClient("http://tools:8200")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        out = [ev async for ev in client.stream({"user_id": 1, "text": "привіт"})]
        await client.aclose()
        return out

    events = asyncio.run(_run())
    assert "".join(e["delta"] for e in events if "delta" in e) == "Привіт"
    assert events[-1]["done"] is True and events[-1]["text"] == "Привіт"


def test_stream_empty_on_missing_fields():
    async def _run() -> list[dict]:
        client = ToolsClient("http://tools:8200")
        out = [ev async for ev in client.stream({})]
        await client.aclose()
        return out

    assert asyncio.run(_run()) == []
