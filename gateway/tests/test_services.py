"""ServicesClient — HTTP-клієнт до Tools/Twin для Telegram-дашборду.

Жодного прямого тесту не існувало, попри fan-in 11 файлів і нетривіальну
логіку: ретраї в `dashboard()`, ланцюжок `promote/rollback → deploy`, та
вкладене вилучення `detail` з помилки у `tools_deploy_lora` (JSON-тіло
проти текстового фолбеку). Тестуємо через `httpx.MockTransport` —
встановлений патерн з `test_tools_client.py` (підміна `._client`/
`._dash_client` мок-транспортованим `AsyncClient`)."""
from __future__ import annotations

import httpx
import pytest
from app.services import ServicesClient


def _client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture()
def svc():
    return ServicesClient("http://tools:8200", "http://twin:8300")


# --- dashboard: ретраї ---

async def test_dashboard_succeeds_first_try(svc):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/dashboard"
        return httpx.Response(200, json={"mode": "chat"})

    svc._dash_client = _client_with(handler)
    assert await svc.dashboard() == {"mode": "chat"}


async def test_dashboard_retries_then_succeeds(svc):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"mode": "agent"})

    svc._dash_client = _client_with(handler)
    assert await svc.dashboard() == {"mode": "agent"}
    assert calls["n"] == 3


async def test_dashboard_all_attempts_fail_returns_unreachable(svc):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    svc._dash_client = _client_with(handler)
    assert await svc.dashboard() == {"error": "tools_unreachable"}
    assert calls["n"] == 3  # рівно 3 спроби, не більше й не менше


# --- прості проксі з толерантним фолбеком ---

async def test_set_mode_success(svc):
    svc._client = _client_with(lambda req: httpx.Response(200, json={"mode": "agent"}))
    assert await svc.set_mode("agent") == {"mode": "agent"}


async def test_set_mode_http_error_returns_error_dict(svc):
    svc._client = _client_with(lambda req: httpx.Response(500))
    out = await svc.set_mode("agent")
    assert "error" in out


async def test_twin_status_http_error_returns_empty_dict(svc):
    svc._client = _client_with(lambda req: httpx.Response(500))
    assert await svc.twin_status() == {}


async def test_twin_lora_versions_http_error_returns_versions_fallback(svc):
    svc._client = _client_with(lambda req: httpx.Response(500))
    out = await svc.twin_lora_versions()
    assert out["versions"] == []
    assert "error" in out


# --- tools_deploy_lora: вилучення detail з помилки ---

async def test_tools_deploy_lora_success(svc):
    svc._client = _client_with(lambda req: httpx.Response(200, json={"ok": True}))
    assert await svc.tools_deploy_lora() == {"ok": True}


async def test_tools_deploy_lora_extracts_json_detail(svc):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "ollama unreachable"})

    svc._client = _client_with(handler)
    out = await svc.tools_deploy_lora()
    assert out == {"ok": False, "error": "ollama unreachable"}


async def test_tools_deploy_lora_falls_back_to_text_when_not_json(svc):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, content=b"<html>Bad Gateway</html>")

    svc._client = _client_with(handler)
    out = await svc.tools_deploy_lora()
    assert out["ok"] is False
    assert "Bad Gateway" in out["error"]


# --- promote/rollback: ланцюжок deploy ---

async def test_twin_promote_lora_chains_into_deploy_when_requested(svc):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/promote"):
            return httpx.Response(200, json={"version": "v2"})
        assert req.url.path == "/lora/deploy"
        return httpx.Response(200, json={"ok": True})

    svc._client = _client_with(handler)
    out = await svc.twin_promote_lora("v2")
    assert out["version"] == "v2"
    assert out["ollama"] == {"ok": True}


async def test_twin_promote_lora_skips_deploy_when_not_requested(svc):
    svc._client = _client_with(lambda req: httpx.Response(200, json={"version": "v2"}))
    out = await svc.twin_promote_lora("v2", deploy=False)
    assert "ollama" not in out


async def test_twin_promote_lora_http_error_returns_error_dict_without_deploy(svc):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    svc._client = _client_with(handler)
    out = await svc.twin_promote_lora("v2")
    assert "error" in out
    assert "ollama" not in out
    assert calls["n"] == 1  # помилка на promote → deploy НЕ викликається


async def test_twin_rollback_lora_chains_into_deploy(svc):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/rollback"):
            assert req.url.params.get("n") == "2"
            return httpx.Response(200, json={"version": "v1"})
        return httpx.Response(200, json={"ok": True})

    svc._client = _client_with(handler)
    out = await svc.twin_rollback_lora(2)
    assert out["version"] == "v1"
    assert out["ollama"] == {"ok": True}
