"""Юніт-тести маппингу tool→endpoint (mocked-httpx, без мережі й без MCP-SDK).

Кодифікують критерії прийняття P1-спеки (docs/JARVIS_CONNECTOR_P1.spec.md).
Ганяти: `pytest .claude/skills/jarvis/connector/tests`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

_CONNECTOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CONNECTOR))

import server  # noqa: E402


# --- порт endpoint: дефолт локальний (S1) ------------------------------------

def test_default_endpoint_is_local_s1() -> None:
    cfg = server.ConnectorConfig.from_env({"JARVIS_API_KEY": "k"})
    assert cfg.base_url == "http://localhost:8000"


# --- порт auth: fail-fast + режими -------------------------------------------

def test_auth_failfast_when_no_credentials() -> None:
    with pytest.raises(server.ConnectorConfigError):
        server.ConnectorConfig.from_env({"JARVIS_BASE_URL": "http://x"})


def test_bearer_header_when_api_key() -> None:
    cfg = server.ConnectorConfig.from_env({"JARVIS_API_KEY": "sk-test"})
    assert cfg.headers()["Authorization"] == "Bearer sk-test"
    assert cfg.httpx_auth() is None


def test_basic_auth_when_password() -> None:
    cfg = server.ConnectorConfig.from_env({"JARVIS_BASIC_PASSWORD": "pw"})
    assert cfg.headers() == {}
    assert isinstance(cfg.httpx_auth(), httpx.BasicAuth)


def test_platform_password_falls_back_to_basic() -> None:
    cfg = server.ConnectorConfig.from_env({"PLATFORM_PASSWORD": "pw"})
    assert isinstance(cfg.httpx_auth(), httpx.BasicAuth)


def test_admin_panel_password_falls_back_to_basic() -> None:
    # gateway приймає ADMIN_PANEL_PASSWORD як альт. browser-пароль (auth.py:active_browser_password)
    cfg = server.ConnectorConfig.from_env({"ADMIN_PANEL_PASSWORD": "pw"})
    assert isinstance(cfg.httpx_auth(), httpx.BasicAuth)


# --- whoami → GET /api/v1/whoami ---------------------------------------------

def test_whoami_maps_to_get_endpoint(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"org_id": "org_x", "user_id": "7",
                                         "role": "owner", "plan": "studio", "via": "basic"})

    calls: list[tuple[object, ...]] = []
    cfg = server.ConnectorConfig.from_env({"JARVIS_BASIC_PASSWORD": "pw",
                                           "JARVIS_CONNECTOR_AUDIT": str(tmp_path / "a.jsonl")})
    client = server.JarvisClient(cfg, transport=httpx.MockTransport(handler),
                                 audit=lambda *a, **k: calls.append(a))
    data = client.whoami()
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/whoami"
    assert seen["auth"].startswith("Basic ")
    assert data["org_id"] == "org_x"
    assert calls and calls[0][0] == "whoami"


# --- chat → POST /api/v1/chat {text, mode} -----------------------------------

def test_chat_maps_to_post_with_body(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"reply": "привіт", "mode": "auto", "via": "basic"})

    cfg = server.ConnectorConfig.from_env({"JARVIS_API_KEY": "k",
                                           "JARVIS_CONNECTOR_AUDIT": str(tmp_path / "a.jsonl")})
    client = server.JarvisClient(cfg, transport=httpx.MockTransport(handler),
                                 audit=lambda *a, **k: None)
    data = client.chat("як справи?", mode="auto")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/chat"
    assert captured["body"] == {"text": "як справи?", "mode": "auto"}
    assert data["reply"] == "привіт"


# --- порт audit: реальний jsonl + anti-leak ----------------------------------

def test_audit_writes_jsonl_and_redacts_payload(tmp_path: Path) -> None:
    secret_in = "SENSITIVE_SECRET_42"
    secret_out = "REPLY_SECRET_99"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": secret_out})

    p = tmp_path / "audit.jsonl"
    cfg = server.ConnectorConfig.from_env({"JARVIS_API_KEY": "k", "JARVIS_CONNECTOR_AUDIT": str(p)})
    client = server.JarvisClient(cfg, transport=httpx.MockTransport(handler))  # реальний audit-sink
    client.chat(secret_in)
    assert p.is_file()
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tool"] == "chat"
    assert "summary" in rec and "tags" in rec
    # сирий вхід/відповідь НЕ потрапляють у слід — лише метадані
    blob = p.read_text(encoding="utf-8")
    assert "chars_in=" in blob
    assert secret_in not in blob
    assert secret_out not in blob


# --- adapter ↔ core: маршрути не дрейфують ------------------------------------

def test_manifest_matches_routes() -> None:
    manifest_path = _CONNECTOR.parent / "adapters" / "jarvis" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes = {k: (v["method"], v["path"]) for k, v in manifest["routes"].items()}
    assert routes == server._ROUTES
    assert manifest["base_url_default"] == server._DEFAULT_BASE_URL


# --- порт capabilities: FastMCP-wiring (skip, якщо MCP-SDK не встановлено) ----

def test_build_server_registers_tools() -> None:
    pytest.importorskip("mcp")
    import asyncio

    cfg = server.ConnectorConfig.from_env({"JARVIS_API_KEY": "k"})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = server.JarvisClient(cfg, transport=httpx.MockTransport(handler), audit=lambda *a, **k: None)
    srv = server.build_server(client=client)
    tools = asyncio.run(srv.list_tools())
    assert sorted(t.name for t in tools) == [
        "chat", "code", "computer", "confirm_approve", "confirm_cancel", "confirm_pending",
        "context_ingest", "context_recent", "context_search",
        "mcp_call", "mcp_list", "whoami",
    ]


def test_mcp_list_is_get(tmp_path: Path) -> None:
    cap: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["method"] = request.method
        cap["path"] = request.url.path
        return httpx.Response(200, json={"servers": ["fs"]})

    out = _client(handler, tmp_path).mcp_list()
    assert cap["method"] == "GET"
    assert cap["path"] == "/api/v1/mcp/servers"
    assert out["servers"] == ["fs"]


def test_redaction_default_on_scrubs_secret(tmp_path: Path) -> None:
    aws = "AKIAIOSFODNN7EXAMPLE"  # канонічний AWS-ключ — ловить і SSOT, і fallback

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": f"your key is {aws}"})

    out = _client(handler, tmp_path).chat("x")  # redact default ON
    assert aws not in str(out["reply"])
    assert "REDACTED" in str(out["reply"])


def test_redaction_opt_out_passes_through(tmp_path: Path) -> None:
    aws = "AKIAIOSFODNN7EXAMPLE"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": f"your key is {aws}"})

    out = _client(handler, tmp_path, JARVIS_REDACT="0").chat("x")
    assert aws in str(out["reply"])


def test_redaction_preserves_uuid_and_numbers(tmp_path: Path) -> None:
    # регрес: card/iban/otp виключені → org_id-UUID і числа НЕ мангліться
    uid = "00000000-0000-0000-0000-000000000001"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"org_id": uid, "plan": "studio", "user_id": "1112730050"})

    out = _client(handler, tmp_path).whoami()
    assert out["org_id"] == uid
    assert out["user_id"] == "1112730050"


def test_mcp_call_posts_server_tool_args(tmp_path: Path) -> None:
    cap: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["path"] = request.url.path
        cap["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "ok"})

    _client(handler, tmp_path).mcp_call("fs", "read", {"p": "x"})
    assert cap["path"] == "/api/v1/mcp/call"
    assert cap["body"] == {"server": "fs", "tool": "read", "arguments": {"p": "x"}}


# --- P2/P3 маппинг нових tool-ів ----------------------------------------------

def _client(handler: object, tmp_path: Path, **env: str) -> "server.JarvisClient":
    base = {"JARVIS_API_KEY": "k", "JARVIS_CONNECTOR_AUDIT": str(tmp_path / "a.jsonl")}
    base.update(env)
    cfg = server.ConnectorConfig.from_env(base)
    return server.JarvisClient(cfg, transport=httpx.MockTransport(handler), audit=lambda *a, **k: None)


def test_context_search_maps_post_body(tmp_path: Path) -> None:
    cap: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["path"] = request.url.path
        cap["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [{"id": 1}]})

    out = _client(handler, tmp_path).context_search("rent topic", top_k=5)
    assert cap["path"] == "/api/v1/context/search"
    assert cap["body"] == {"query": "rent topic", "top_k": 5, "tags": None, "since": None}
    assert len(out["results"]) == 1


def test_context_ingest_wraps_single_event(tmp_path: Path) -> None:
    cap: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["path"] = request.url.path
        cap["body"] = json.loads(request.content)
        return httpx.Response(200, json={"accepted": 1, "duplicates": 0})

    _client(handler, tmp_path).context_ingest("important note", kind="note", tags=["topic:rent"])
    assert cap["path"] == "/api/v1/ingest/events"
    body = cap["body"]
    assert isinstance(body, dict) and len(body["events"]) == 1
    assert body["events"][0]["summary"] == "important note"


def test_code_maps_post_with_target(tmp_path: Path) -> None:
    cap: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["path"] = request.url.path
        cap["body"] = json.loads(request.content)
        return httpx.Response(200, json={"reply": "ok", "target": "local"})

    _client(handler, tmp_path).code("додай тест", target="local")
    assert cap["path"] == "/api/v1/code/task"
    assert cap["body"] == {"text": "додай тест", "target": "local"}


def test_confirm_pending_is_get(tmp_path: Path) -> None:
    cap: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["method"] = request.method
        cap["path"] = request.url.path
        return httpx.Response(200, json={"pending": False})

    _client(handler, tmp_path).confirm_pending()
    assert cap["method"] == "GET"
    assert cap["path"] == "/api/v1/confirm/pending"


def test_confirm_approve_posts_code(tmp_path: Path) -> None:
    cap: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap["path"] = request.url.path
        cap["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    _client(handler, tmp_path).confirm_approve("1234")
    assert cap["path"] == "/api/v1/confirm/approve"
    assert cap["body"] == {"code": "1234"}


# --- .env fallback (детерміновано через tmp) ----------------------------------

def test_repo_env_password_platform_priority(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text('ADMIN_PANEL_PASSWORD="aaa"\nPLATFORM_PASSWORD=bbb\n', encoding="utf-8")
    assert server._repo_env_password(f) == "bbb"


def test_repo_env_password_admin_fallback(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("# comment\nADMIN_PANEL_PASSWORD=zzz\n", encoding="utf-8")
    assert server._repo_env_password(f) == "zzz"


def test_repo_env_password_absent(tmp_path: Path) -> None:
    assert server._repo_env_password(tmp_path / "nope.env") is None


def test_explicit_env_does_not_use_env_file(tmp_path: Path) -> None:
    # явний env-словник без creds → fail-fast (НЕ читаємо репо-.env), детерміновано
    with pytest.raises(server.ConnectorConfigError):
        server.ConnectorConfig.from_env({"JARVIS_BASE_URL": "http://x"})
