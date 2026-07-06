"""R2 «Тонкий шлюз»: юніт-тести спільного внутрішнього RPC-helper-а.

Критерії §1 спеки: уніфікований error-envelope, per-call таймаути, ретраї
на транспорт/502-504. Транспорт мокається через httpx.MockTransport (DI `client`).
"""
from __future__ import annotations

import httpx
import pytest

from jarvis_core.service_client import ServiceError, call, call_dict


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_call_returns_parsed_json():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path == "/context/store"
        return httpx.Response(200, json={"ok": True, "id": 7})

    async with _client(handler) as cli:
        out = await call(
            "http://memory:8100/", "post", "/context/store",
            json={"x": 1}, service="memory", client=cli,
        )
    assert out == {"ok": True, "id": 7}


async def test_call_dict_coerces_non_dict_json():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    async with _client(handler) as cli:
        out = await call_dict("http://tools:8200", "GET", "/list", client=cli)
    assert out == {}


async def test_http_error_becomes_envelope_with_status_and_detail():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "project not found"})

    async with _client(handler) as cli:
        with pytest.raises(ServiceError) as ei:
            await call("http://memory:8100", "GET", "/projects/9", service="memory", client=cli)
    err = ei.value
    assert err.status == 404
    assert err.detail == "project not found"
    assert "memory GET /projects/9" in str(err)


async def test_transport_error_becomes_envelope_without_status():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("all down")

    async with _client(handler) as cli:
        with pytest.raises(ServiceError) as ei:
            await call("http://tools:8200", "GET", "/dashboard", service="tools", client=cli)
    assert ei.value.status is None
    assert "unreachable" in str(ei.value)


async def test_retry_on_503_then_success():
    attempts: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as cli:
        out = await call(
            "http://tools:8200", "GET", "/dashboard",
            retries=3, retry_backoff=0.0, client=cli,
        )
    assert out == {"ok": True}
    assert len(attempts) == 3


async def test_retry_on_transport_error_then_success():
    attempts: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as cli:
        out = await call(
            "http://twin:8765", "GET", "/status",
            retries=1, retry_backoff=0.0, client=cli,
        )
    assert out == {"ok": True}
    assert len(attempts) == 2


async def test_no_retry_by_default():
    attempts: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    async with _client(handler) as cli:
        with pytest.raises(ServiceError) as ei:
            await call("http://tools:8200", "GET", "/dashboard", client=cli)
    assert ei.value.status == 503
    assert len(attempts) == 1


async def test_custom_retry_statuses_widen_retry():
    attempts: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(500)  # не в дефолтному наборі 502/503/504
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as cli:
        out = await call(
            "http://tools:8200", "GET", "/dashboard",
            retries=2, retry_backoff=0.0, retry_statuses=range(400, 600), client=cli,
        )
    assert out == {"ok": True}
    assert len(attempts) == 3


async def test_4xx_is_not_retried():
    attempts: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(400, json={"detail": "bad"})

    async with _client(handler) as cli:
        with pytest.raises(ServiceError):
            await call("http://memory:8100", "POST", "/x", retries=2, retry_backoff=0.0, client=cli)
    assert len(attempts) == 1


async def test_invalid_json_body_is_envelope():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    async with _client(handler) as cli:
        with pytest.raises(ServiceError) as ei:
            await call("http://tools:8200", "GET", "/x", client=cli)
    assert ei.value.status == 200
    assert "invalid JSON" in ei.value.detail
