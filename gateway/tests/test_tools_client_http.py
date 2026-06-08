"""tools_request — спільний httpx boilerplate для ToolsClient (єдина точка входу).

`ToolsClient._request` (а через неї — ~30 методів `ToolsClient`) проходить
через ЦЮ єдину функцію, але прямого тесту не було: лише непряме покриття
там, де `test_tools_client.py` випадково зачіпає вдалий шлях. Тут — фокус
саме на умовній побудові kwargs (json/params/timeout пропускаються, якщо
None — а не передаються як `None`, що для деяких httpx-версій важливо) і
на толерантному `None`-фолбеку при `httpx.HTTPError`."""
from __future__ import annotations

import httpx

from app.tools_client_http import tools_request


def _client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_builds_url_from_base_and_relative_path():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/agent/plan/p1"
        return httpx.Response(200, json={"ok": True})

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200", "GET", "/agent/plan/p1")
    assert resp is not None
    assert resp.status_code == 200


async def test_strips_trailing_slash_from_base():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/mode"
        return httpx.Response(200, json={})

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200/", "GET", "/mode")
    assert resp is not None


async def test_passes_json_when_given():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.content == b'{"mode":"agent"}'
        return httpx.Response(200, json={})

    async with _client_with(handler) as cli:
        resp = await tools_request(
            cli, "http://tools:8200", "POST", "/mode", json={"mode": "agent"}
        )
    assert resp is not None


async def test_omits_json_when_none():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.content == b""
        return httpx.Response(200, json={})

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200", "POST", "/mode")
    assert resp is not None


async def test_passes_params_when_given():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params.get("limit") == "5"
        return httpx.Response(200, json={})

    async with _client_with(handler) as cli:
        resp = await tools_request(
            cli, "http://tools:8200", "GET", "/plans", params={"limit": 5}
        )
    assert resp is not None


async def test_uppercases_method():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        return httpx.Response(200, json={})

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200", "delete", "/mode")
    assert resp is not None


async def test_returns_none_on_http_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200", "GET", "/dashboard")
    assert resp is None


async def test_returns_response_even_for_error_status_no_raise():
    # tools_request НЕ викликає raise_for_status — викликач сам вирішує
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    async with _client_with(handler) as cli:
        resp = await tools_request(cli, "http://tools:8200", "GET", "/agent/plan/x")
    assert resp is not None
    assert resp.status_code == 404
