"""Юніт-тести MCP-адаптера erp_sa (mocked-httpx, без мережі/VPN/Chrome, без MCP-SDK).

Кодифікують критерії P1 концепту (docs/ERP_SA_AUTOFILL_CONCEPT.md).
Ганяти: `pytest .claude/skills/erp_sa/engine/tests -q`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ENGINE))

import server  # noqa: E402


# --- fixtures/helpers ---------------------------------------------------------

_ALLOW = ("https://erp.sparrow-avia.tech/import/*",)


def _adapter(allowlist: tuple[str, ...] = _ALLOW) -> "server.Adapter":
    return server.Adapter(
        base_url="https://erp.sparrow-avia.tech",
        allowlist=allowlist,
        field_aliases={
            "doc_number": ["номер", "№", "number"],
            "doc_date": ["дата", "date"],
            "counterparty": ["контрагент", "supplier"],
        },
        route_map={"invoice": "/import/index"},
    )


def _cfg(tmp_path: Path, **env: str) -> "server.GatewayConfig":
    base = {"ERP_SA_API_KEY": "k", "ERP_SA_AUDIT": str(tmp_path / "a.jsonl"),
            "ERP_SA_POLL_INTERVAL": "0", "ERP_SA_POLL_ATTEMPTS": "3"}
    base.update(env)
    return server.GatewayConfig.from_env(base)


def _handler(
    *, current_url: str = "https://erp.sparrow-avia.tech/import/index",
    form_schema: list[dict[str, Any]] | None = None,
    chat_reply: str = "{}", fill_ok: bool = True,
) -> Callable[[httpx.Request], httpx.Response]:
    """Мокає gateway: /chat, /chrome/command→/chrome/result/{id}, /confirm/*."""
    state: dict[str, dict[str, Any]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/chat":
            return httpx.Response(200, json={"reply": chat_reply, "mode": "chat", "via": "basic"})
        if path == "/api/v1/chrome/command":
            body = json.loads(request.content)
            cmd_id = "cmd1"
            action = body.get("action")
            if action == "location":                       # CSP-safe дія → рядок URL
                result: Any = current_url
            elif action == "schema":                       # extension віддає JSON-РЯДОК
                result = json.dumps(form_schema if form_schema is not None else [])
            elif action == "fill":
                result = "filled" if fill_ok else "no-element"
            else:
                result = "ok"
            state[cmd_id] = {"ok": fill_ok if action == "fill" else True, "result": result}
            return httpx.Response(200, json={"id": cmd_id, "queued": True})
        if path.startswith("/api/v1/chrome/result/"):
            cmd_id = path.rsplit("/", 1)[-1]
            st = state.get(cmd_id)
            if st is None:
                return httpx.Response(200, json={"status": "pending"})
            return httpx.Response(200, json={"status": "done", **st})
        if path.startswith("/api/v1/confirm/"):
            return httpx.Response(200, json={"pending": False, "ok": True})
        return httpx.Response(404, json={})

    return handler


def _client(cfg: "server.GatewayConfig", handler: Callable[[httpx.Request], httpx.Response],
            audit: Callable[..., None] | None = None) -> "server.GatewayClient":
    return server.GatewayClient(cfg, transport=httpx.MockTransport(handler),
                                audit=audit or (lambda *a, **k: None), sleep=lambda _s: None)


# --- порт endpoint/auth: дефолт локальний (S1) + fail-fast --------------------

def test_default_endpoint_is_local_s1() -> None:
    cfg = server.GatewayConfig.from_env({"ERP_SA_API_KEY": "k"})
    assert cfg.base_url == "http://localhost:8000"


def test_auth_failfast_when_no_credentials() -> None:
    with pytest.raises(server.GatewayConfigError):
        server.GatewayConfig.from_env({"ERP_SA_BASE_URL": "http://x"})


def test_jarvis_env_is_reused_for_shared_gateway() -> None:
    cfg = server.GatewayConfig.from_env({"JARVIS_BASIC_PASSWORD": "pw"})
    assert isinstance(cfg.httpx_auth(), httpx.BasicAuth)


# --- blast-radius: deny-wins, fail-closed (S5) -------------------------------

def test_url_allowed_matches_import_route() -> None:
    assert server.url_allowed("https://erp.sparrow-avia.tech/import/index", _ALLOW)
    assert server.url_allowed("https://erp.sparrow-avia.tech/import/goods?id=7", _ALLOW)


def test_url_allowed_denies_other_pages() -> None:
    assert not server.url_allowed("https://erp.sparrow-avia.tech/admin/users", _ALLOW)
    assert not server.url_allowed("https://evil.example.com/import/index", _ALLOW)


def test_url_allowed_empty_allowlist_denies_all() -> None:
    assert not server.url_allowed("https://erp.sparrow-avia.tech/import/index", ())
    assert not server.url_allowed("", _ALLOW)


def test_fill_refuses_off_allowlist_page(tmp_path: Path) -> None:
    cli = _client(_cfg(tmp_path), _handler(current_url="https://erp.sparrow-avia.tech/admin/users"))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    with pytest.raises(server.BlastRadiusError):
        eng.fill([{"selector": "#num", "value": "INV-1"}])


def test_inspect_form_navigate_refuses_off_allowlist(tmp_path: Path) -> None:
    cli = _client(_cfg(tmp_path), _handler())
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    with pytest.raises(server.BlastRadiusError):
        eng.inspect_form(url="https://erp.sparrow-avia.tech/admin")


# --- map (порт map): синоніми полів, ніколи не вигадуємо ----------------------

def test_map_fields_matches_by_alias_and_name() -> None:
    schema = [
        {"selector": "#num", "name": "doc_number", "id": "num", "label": "Номер"},
        {"selector": "#dt", "name": "date", "id": "dt", "label": "Дата"},
        {"selector": "#cp", "name": "supplier", "id": "cp", "label": "Постачальник"},
    ]
    fields = {"doc_number": "INV-7", "doc_date": "2026-07-01", "counterparty": "ТОВ Х"}
    fill, unmapped = server.map_fields(fields, schema, _adapter().field_aliases)
    by_src = {f["source_field"]: f["selector"] for f in fill}
    assert by_src == {"doc_number": "#num", "doc_date": "#dt", "counterparty": "#cp"}
    assert unmapped == []


def test_map_fields_reports_unmapped_and_skips_empty() -> None:
    schema = [{"selector": "#num", "name": "doc_number", "id": "num", "label": "Номер"}]
    fields = {"doc_number": "INV-7", "doc_date": "", "counterparty": "ТОВ Х"}
    fill, unmapped = server.map_fields(fields, schema, _adapter().field_aliases)
    assert [f["selector"] for f in fill] == ["#num"]  # doc_date порожнє → пропущено, не в unmapped
    assert unmapped == ["counterparty"]               # нема поля у формі → чесно unmapped


def test_map_fields_one_selector_used_once() -> None:
    schema = [{"selector": "#x", "name": "num", "id": "x", "label": "Номер / дата"}]
    fields = {"doc_number": "A", "doc_date": "B"}
    fill, _ = server.map_fields(fields, schema, _adapter().field_aliases)
    assert len({f["selector"] for f in fill}) == len(fill)  # без дублювання селектора


# --- locate/schema: JSON-рядок від extension коректно парситься -----------------

def test_coerce_schema_handles_json_string_list_garbage() -> None:
    js = '[{"selector":"#a","name":"n"}]'
    assert server._coerce_schema(js) == [{"selector": "#a", "name": "n"}]         # JSON-рядок
    assert server._coerce_schema([{"selector": "#b"}]) == [{"selector": "#b"}]    # вже list
    assert server._coerce_schema("[object Object]") == []                          # сміття (старий баг)
    assert server._coerce_schema(None) == []


def test_inspect_form_parses_extension_json_string(tmp_path: Path) -> None:
    # extension повертає JSON-РЯДОК (через `schema`-дію), не масив — inspect_form має його розпарсити
    schema = [{"selector": "#num", "name": "doc_number", "id": "num", "label": "Номер"}]
    cli = _client(_cfg(tmp_path), _handler(form_schema=schema))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    out = eng.inspect_form()
    assert out == schema and isinstance(out, list)


# --- recognize (порт recognize): JSON-парс, лише поля -------------------------

def test_parse_json_block_tolerates_prose_and_fences() -> None:
    assert server._parse_json_block('ось дані: {"a": 1} готово')["a"] == 1
    assert server._parse_json_block('```json\n{"b": 2}\n```')["b"] == 2
    assert server._parse_json_block("не json") == {}


def test_recognize_extracts_fields(tmp_path: Path) -> None:
    reply = '{"doc_number":"INV-7","doc_date":"2026-07-01","doc_type":"invoice","confidence":0.9}'
    cli = _client(_cfg(tmp_path), _handler(chat_reply=reply))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    out = eng.recognize("Інвойс № INV-7 від 2026-07-01")
    assert out["doc_type"] == "invoice"
    assert out["fields"] == {"doc_number": "INV-7", "doc_date": "2026-07-01"}


def test_recognize_rejects_empty(tmp_path: Path) -> None:
    eng = server.Engine(_client(_cfg(tmp_path), _handler()), _adapter(), audit=lambda *a, **k: None)
    with pytest.raises(server.RecognizeError):
        eng.recognize("   ")


# --- ingest (порт ingest): цифровий файл → текст ------------------------------

def test_extract_text_txt_and_csv(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Інвойс № INV-7", encoding="utf-8")
    assert "INV-7" in server.extract_source_text(tmp_path / "a.txt")
    (tmp_path / "b.csv").write_text("номер,дата\nINV-7,2026-07-01\n", encoding="utf-8")
    out = server.extract_source_text(tmp_path / "b.csv")
    assert "INV-7" in out and "2026-07-01" in out


def test_extract_text_scan_needs_vision(tmp_path: Path) -> None:
    (tmp_path / "scan.jpg").write_bytes(b"\xff\xd8\xff")
    with pytest.raises(server.RecognizeError, match="vision"):
        server.extract_source_text(tmp_path / "scan.jpg")


def test_extract_text_unsupported_and_missing(tmp_path: Path) -> None:
    (tmp_path / "x.zip").write_bytes(b"PK")
    with pytest.raises(server.RecognizeError, match="unsupported"):
        server.extract_source_text(tmp_path / "x.zip")
    with pytest.raises(server.RecognizeError, match="not found"):
        server.extract_source_text(tmp_path / "nope.txt")


def test_recognize_from_file_source(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("Інвойс № INV-9 контрагент ТОВ Х", encoding="utf-8")
    reply = '{"doc_number":"INV-9","counterparty":"ТОВ Х","doc_type":"invoice","confidence":0.7}'
    cli = _client(_cfg(tmp_path), _handler(chat_reply=reply))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    out = eng.recognize(source_path=str(tmp_path / "doc.txt"))
    assert out["fields"]["doc_number"] == "INV-9"


# --- chrome-міст: command → poll result --------------------------------------

def test_chrome_bridge_command_then_poll(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/v1/chrome/command":
            return httpx.Response(200, json={"id": "c9"})
        return httpx.Response(200, json={"status": "done", "ok": True, "result": "https://x"})

    cli = _client(_cfg(tmp_path), handler)
    out = cli.chrome("eval", script="window.location.href")
    assert out == {"ok": True, "result": "https://x"}
    assert "/api/v1/chrome/command" in seen and any("/chrome/result/" in p for p in seen)


def test_chrome_bridge_timeout_raises(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/chrome/command":
            return httpx.Response(200, json={"id": "c9"})
        return httpx.Response(200, json={"status": "pending"})  # ніколи не done → таймаут

    cli = _client(_cfg(tmp_path), handler)
    with pytest.raises(server.ChromeBridgeError):
        cli.chrome("fill", selector="#x", value="v")


# --- autofill happy-path: dry_run + повний ------------------------------------

def test_autofill_dry_run_returns_mapping_without_filling(tmp_path: Path) -> None:
    schema = [
        {"selector": "#num", "name": "doc_number", "id": "num", "label": "Номер"},
        {"selector": "#dt", "name": "date", "id": "dt", "label": "Дата"},
    ]
    reply = '{"doc_number":"INV-7","doc_date":"2026-07-01","doc_type":"invoice","confidence":0.8}'
    cli = _client(_cfg(tmp_path), _handler(form_schema=schema, chat_reply=reply))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    out = eng.autofill("Інвойс INV-7", dry_run=True)
    assert out["dry_run"] is True
    assert "filled" not in out
    assert {f["source_field"] for f in out["form_fill"]} == {"doc_number", "doc_date"}


def test_autofill_fill_mode_fills_on_allowed_page(tmp_path: Path) -> None:
    schema = [{"selector": "#num", "name": "doc_number", "id": "num", "label": "Номер"}]
    reply = '{"doc_number":"INV-7","doc_type":"invoice","confidence":0.8}'
    cli = _client(_cfg(tmp_path), _handler(form_schema=schema, chat_reply=reply))
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    out = eng.autofill("Інвойс INV-7", dry_run=False)
    assert out["filled"] == ["#num"]
    assert "S4" in out["note"]  # нагадування, що submit — за людиною


# --- порт audit: anti-leak (лише метадані, не сирий документ) -----------------

def test_audit_never_leaks_document_text(tmp_path: Path) -> None:
    secret = "СЕКРЕТНА_КОМЕРЦІЙНА_ТАЄМНИЦЯ_42"
    reply = '{"doc_number":"INV-7","doc_type":"invoice","confidence":0.9}'
    p = tmp_path / "audit.jsonl"
    cfg = _cfg(tmp_path, ERP_SA_AUDIT=str(p))
    cli = server.GatewayClient(cfg, transport=httpx.MockTransport(_handler(chat_reply=reply)),
                               sleep=lambda _s: None)  # реальний audit-sink
    eng = server.Engine(cli, _adapter())  # реальний audit
    eng.recognize(f"Документ. {secret}. Кінець.")
    blob = p.read_text(encoding="utf-8")
    assert "doc_type=invoice" in blob       # метадані є
    assert secret not in blob               # сирий вміст — ні


# --- adapter ↔ engine: маніфест вантажиться, allowlist/aliases не порожні ------

def test_real_manifest_loads() -> None:
    adp = server.Adapter.load()
    assert adp.base_url == "https://erp.sparrow-avia.tech"
    assert any("import" in a for a in adp.allowlist)
    assert "doc_number" in adp.field_aliases          # seed-поля без "_"-ключів
    assert all(not k.startswith("_") for k in adp.field_aliases)


# --- порт capabilities: FastMCP-wiring (skip без MCP-SDK) ---------------------

def test_build_server_registers_tools(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import asyncio

    cli = _client(_cfg(tmp_path), _handler())
    eng = server.Engine(cli, _adapter(), audit=lambda *a, **k: None)
    srv = server.build_server(engine=eng)
    tools = asyncio.run(srv.list_tools())
    assert sorted(t.name for t in tools) == [
        "autofill", "confirm_approve", "confirm_cancel", "confirm_pending",
        "fill", "inspect_form", "locate", "ready", "recognize",
    ]


# --- readiness + locate -------------------------------------------------------

def test_ready_reports_gateway_and_bridge(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/whoami":
            return httpx.Response(200, json={"org_id": "org_x", "via": "basic"})
        if request.url.path == "/api/v1/chrome/command":
            return httpx.Response(200, json={"id": "c1"})
        return httpx.Response(200, json={"status": "done", "ok": True,
                                         "result": "https://erp.sparrow-avia.tech/import/index"})

    eng = server.Engine(_client(_cfg(tmp_path), handler), _adapter(), audit=lambda *a, **k: None)
    out = eng.ready()
    assert out["gateway"] is True and out["chrome_bridge"] is True
    assert out["on_allowlisted_page"] is True and out["ready"] is True


def test_ready_degrades_when_bridge_down(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/whoami":
            return httpx.Response(200, json={"org_id": "org_x", "via": "basic"})
        if request.url.path == "/api/v1/chrome/command":
            return httpx.Response(200, json={"id": "c1"})
        return httpx.Response(200, json={"status": "pending"})  # extension не піднято → таймаут

    eng = server.Engine(_client(_cfg(tmp_path), handler), _adapter(), audit=lambda *a, **k: None)
    out = eng.ready()
    assert out["gateway"] is True and out["chrome_bridge"] is False and out["ready"] is False
    assert "chrome_bridge_error" in out


def test_locate_maps_doc_type_to_url(tmp_path: Path) -> None:
    eng = server.Engine(_client(_cfg(tmp_path), _handler()), _adapter(), audit=lambda *a, **k: None)
    out = eng.locate("invoice")
    assert out["url"] == "https://erp.sparrow-avia.tech/import/index"
    assert out["known"] is True and out["allowed"] is True
    assert eng.locate("unknown_type")["known"] is False
