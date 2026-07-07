"""Юніт-тести MCP-рушія ai_tester (mocked-httpx, без мережі, без MCP-SDK).

Кодифікують контракт портів: source-декоратори (підміна джерела даних), oracle,
bounded test→fix→retest луп із S4 (ніколи не авто-апрув), anti-leak audit/report.
Ганяти: `pytest .claude/skills/ai_tester/engine/tests -q`
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

_ENGINE = Path(__file__).resolve().parents[1]

# Унікальне імʼя модуля (НЕ `import server`): у комбінованому прогоні з erp_sa/jarvis їхній
# `server` уже сидить у sys.modules — plain import підхопив би чужий рушій.
_spec = importlib.util.spec_from_file_location("ai_tester_server", _ENGINE / "server.py")
assert _spec is not None and _spec.loader is not None
server = importlib.util.module_from_spec(_spec)
sys.modules["ai_tester_server"] = server
_spec.loader.exec_module(server)


# --- fixtures/helpers ---------------------------------------------------------

def _feature(name: str = "whoami", **over: Any) -> "server.Feature":
    base: dict[str, Any] = dict(
        name=name, title=name, method="GET", path="/api/v1/whoami", request=None,
        gate_flag="", gated_statuses=(), mutating=False,
        oracle={"ok_status": [200], "require_fields": ["org_id"], "nonempty_fields": [],
                "forbid_fields": [], "latency_budget_ms": 0},
        sim={"status": 200, "data": {"org_id": "org_x", "via": "basic"}},
        dispatch_kind="code", on_fail_hint="перевір deps.py",
    )
    base.update(over)
    return server.Feature(**base)


def _adapter(*feats: "server.Feature") -> "server.Adapter":
    items = feats or (_feature(),)
    return server.Adapter(profile="jarvis", base_url_default="http://localhost:8000",
                          features={f.name: f for f in items})


def _cfg(tmp_path: Path, **env: str) -> "server.TesterConfig":
    base = {"AI_TESTER_API_KEY": "k", "AI_TESTER_AUDIT": str(tmp_path / "audit.jsonl"),
            "AI_TESTER_ARTIFACTS": str(tmp_path / "artifacts"), "AI_TESTER_MAX_ROUNDS": "3"}
    base.update(env)
    return server.TesterConfig.from_env(base)


def _http(cfg: "server.TesterConfig", handler: Callable[[httpx.Request], httpx.Response],
          audit: Callable[..., None] | None = None) -> "server.GatewayHttp":
    return server.GatewayHttp(cfg, transport=httpx.MockTransport(handler),
                              audit=audit or (lambda *a, **k: None))


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"org_id": "org_x", "via": "basic"})


def _engine(tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response],
            adapter: "server.Adapter" | None = None,
            audit: Callable[..., None] | None = None) -> "server.Engine":
    return server.Engine(_http(_cfg(tmp_path), handler, audit=audit),
                         adapter or _adapter(), audit=audit or (lambda *a, **k: None))


# --- порти endpoint/auth: дефолт локальний (S1) + fail-fast --------------------

def test_default_endpoint_is_local_s1() -> None:
    cfg = server.TesterConfig.from_env({"AI_TESTER_API_KEY": "k"})
    assert cfg.base_url == "http://localhost:8000"


def test_auth_failfast_when_no_credentials() -> None:
    with pytest.raises(server.TesterConfigError):
        server.TesterConfig.from_env({"AI_TESTER_BASE_URL": "http://x"})


def test_jarvis_env_is_reused_for_shared_gateway() -> None:
    cfg = server.TesterConfig.from_env({"JARVIS_BASIC_PASSWORD": "pw"})
    assert isinstance(cfg.httpx_auth(), httpx.BasicAuth)


def test_max_rounds_must_be_positive_failfast() -> None:
    with pytest.raises(server.TesterConfigError):
        server.TesterConfig.from_env({"AI_TESTER_API_KEY": "k", "AI_TESTER_MAX_ROUNDS": "0"})


def test_repo_env_password_survives_powershell_bom(tmp_path: Path) -> None:
    # PowerShell відрощує BOM у .env — ключ на ПЕРШОМУ рядку не має губитись (utf-8-sig)
    f = tmp_path / ".env"
    f.write_bytes(b"\xef\xbb\xbfPLATFORM_PASSWORD=pw-bom\n")
    assert server._repo_env_password(f) == "pw-bom"


# --- порт source: ланцюжок ДЕКОРАТОРІВ підміняє джерело даних ------------------

def test_replay_source_substitutes_fixture_without_network(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)  # не має бути викликів — джерело підмінене
        return httpx.Response(500, json={})

    feat = _feature()
    src = server.ReplaySource(server.HttpSource(_http(_cfg(tmp_path), handler)),
                              {"whoami": {"status": 200, "data": {"org_id": "sim"}}})
    out = src.send(feat)
    assert out.status == 200 and out.data == {"org_id": "sim"}
    assert calls == []  # декоратор ПІДМІНИВ джерело — мережа не чіпалась


def test_replay_source_delegates_when_no_fixture(tmp_path: Path) -> None:
    src = server.ReplaySource(server.HttpSource(_http(_cfg(tmp_path), _ok_handler)), {})
    out = src.send(_feature())
    assert out.status == 200 and out.data["org_id"] == "org_x"  # делегат у живе джерело


def test_replay_source_bad_fixture_status_failfast(tmp_path: Path) -> None:
    src = server.ReplaySource(server.HttpSource(_http(_cfg(tmp_path), _ok_handler)),
                              {"whoami": {"status": "ok", "data": {}}})
    with pytest.raises(server.ScenarioError, match="not an int"):
        src.send(_feature())


def test_fault_source_injects_each_known_fault(tmp_path: Path) -> None:
    inner = server.HttpSource(_http(_cfg(tmp_path), _ok_handler))
    feat = _feature()
    assert server.FaultSource(inner, "http_500").send(feat).status == 500
    assert server.FaultSource(inner, "http_404").send(feat).status == 404
    assert "transport" in server.FaultSource(inner, "timeout").send(feat).error
    assert server.FaultSource(inner, "malformed").send(feat).error == "non-json response"
    assert server.FaultSource(inner, "empty_reply").send(feat).data == {"reply": ""}
    assert server.FaultSource(inner, "http_500").send(feat).injected is True
    with pytest.raises(server.ScenarioError):
        server.FaultSource(inner, "nope")


def test_fault_source_only_scopes_injection(tmp_path: Path) -> None:
    inner = server.HttpSource(_http(_cfg(tmp_path), _ok_handler))
    src = server.FaultSource(inner, "http_500", only={"chat"})
    assert src.send(_feature("whoami")).status == 200   # не в only → делегат
    assert src.send(_feature("chat")).status == 500     # в only → інʼєкція


def test_recording_source_captures_live_responses(tmp_path: Path) -> None:
    rec = server.RecordingSource(server.HttpSource(_http(_cfg(tmp_path), _ok_handler)))
    rec.send(_feature())
    assert rec.records["whoami"] == {"status": 200, "data": {"org_id": "org_x", "via": "basic"}}


def test_decorator_chain_composes_and_reports(tmp_path: Path) -> None:
    src = server.FaultSource(
        server.ReplaySource(server.HttpSource(_http(_cfg(tmp_path), _ok_handler)), {}),
        "timeout", only=set())
    assert src.chain() == ["FaultSource(timeout)", "ReplaySource", "HttpSource"]


# --- порт oracle: pure-оцінка ---------------------------------------------------

def test_oracle_pass_on_ok_response() -> None:
    v = server.evaluate_feature(_feature(), server.SourceResult(200, {"org_id": "x"}, "", 10))
    assert v["status"] == "pass" and v["reasons"] == []


def test_oracle_fails_on_missing_and_empty_and_forbidden_fields() -> None:
    feat = _feature(oracle={"ok_status": [200], "require_fields": ["org_id"],
                            "nonempty_fields": ["reply"], "forbid_fields": ["error"],
                            "latency_budget_ms": 0})
    v = server.evaluate_feature(feat, server.SourceResult(200, {"reply": " ", "error": "x"}, "", 5))
    assert v["status"] == "fail"
    assert any("org_id" in r for r in v["reasons"])
    assert any("reply" in r for r in v["reasons"])
    assert any("error" in r for r in v["reasons"])


def test_oracle_gated_flag_turns_404_into_skip_not_fail() -> None:
    gated = _feature("context_search", gate_flag="ENABLE_CONTEXT_API", gated_statuses=(404,))
    v = server.evaluate_feature(gated, server.SourceResult(404, {}, "", 5))
    assert v["status"] == "skipped_gated"
    ungated = _feature()  # без прапора той самий 404 = падіння
    assert server.evaluate_feature(ungated, server.SourceResult(404, {}, "", 5))["status"] == "fail"


def test_oracle_injected_fault_never_masquerades_as_gate() -> None:
    # симульований outage (FaultSource) на гейтованій фічі має бути ВИДИМИМ fail, не skipped_gated
    gated = _feature("context_search", gate_flag="ENABLE_CONTEXT_API", gated_statuses=(404,))
    injected = server.SourceResult(404, {"detail": "injected fault"}, "", 0, injected=True)
    assert server.evaluate_feature(gated, injected)["status"] == "fail"


def test_oracle_latency_budget_and_transport_error() -> None:
    slow = _feature(oracle={"ok_status": [200], "require_fields": [], "nonempty_fields": [],
                            "forbid_fields": [], "latency_budget_ms": 100})
    v = server.evaluate_feature(slow, server.SourceResult(200, {"org_id": "x"}, "", 500))
    assert v["status"] == "fail" and any("повільно" in r for r in v["reasons"])
    t = server.evaluate_feature(_feature(), server.SourceResult(0, {}, "transport: ConnectTimeout", 1))
    assert t["status"] == "fail" and "transport" in t["reasons"][0]


def test_verdict_never_leaks_raw_values() -> None:
    secret = "SUPER_SECRET_VALUE_42"
    v = server.evaluate_feature(_feature(), server.SourceResult(200, {"org_id": secret}, "", 1))
    assert secret not in json.dumps(v, ensure_ascii=False)  # лише імена ключів, не значення


# --- run: suite → вердикти + артефакт-звіт --------------------------------------

def test_run_suite_green_and_writes_report(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    out = eng.run()
    assert out["summary"] == {"pass": 1, "fail": 0, "skipped_gated": 0}
    assert Path(out["report_path"]).is_file()
    last = json.loads((tmp_path / "artifacts" / "last_run.json").read_text(encoding="utf-8"))
    assert last["run_id"] == out["run_id"]


def test_run_suite_skips_mutating_by_default(tmp_path: Path) -> None:
    adp = _adapter(_feature(), _feature("code_task", method="POST", path="/api/v1/code/task",
                                        mutating=True))
    eng = _engine(tmp_path, _ok_handler, adapter=adp)
    names = [v["feature"] for v in eng.run()["verdicts"]]
    assert names == ["whoami"]  # mutating — лише явно (S4-дисципліна)
    names_incl = [v["feature"] for v in eng.run(include_mutating=True)["verdicts"]]
    assert "code_task" in names_incl


def test_run_replay_mode_is_offline_deterministic(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway лежить")  # replay не має його чіпати

    eng = _engine(tmp_path, handler)
    out = eng.run(mode="replay")
    assert out["summary"]["fail"] == 0
    assert "ReplaySource" in out["source_chain"]


def test_run_record_mode_saves_fixtures(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    out = eng.run(mode="record")
    recorded = json.loads(Path(out["recorded_path"]).read_text(encoding="utf-8"))
    assert recorded["whoami"]["data"]["org_id"] == "org_x"


def test_run_unknown_mode_or_feature_failfast(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    with pytest.raises(server.ScenarioError):
        eng.run(mode="yolo")
    with pytest.raises(server.ScenarioError):
        eng.run(feature="ghost")


# --- simulate: явна підміна джерела (декоратор) ----------------------------------

def test_simulate_with_explicit_fixture_overrides_source(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("не має викликатись")

    eng = _engine(tmp_path, handler)
    out = eng.simulate("whoami", fixture_json='{"status": 200, "data": {"org_id": "fx"}}')
    assert out["verdict"]["status"] == "pass"
    assert out["source_chain"][0] == "ReplaySource"
    assert "S2" in out["note"]


def test_simulate_wraps_bare_body_and_rejects_bad_json(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    out = eng.simulate("whoami", fixture_json='{"org_id": "bare"}')  # тіло без обгортки → 200
    assert out["verdict"]["status"] == "pass"
    with pytest.raises(server.ScenarioError):
        eng.simulate("whoami", fixture_json="{не json")


def test_simulate_body_with_string_status_is_body_not_wrapper(tmp_path: Path) -> None:
    # JARVIS сам повертає тіла з рядковим status (auth/telegram/poll) — це ТІЛО, не обгортка
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("не має викликатись")

    eng = _engine(tmp_path, handler)
    out = eng.simulate("whoami", fixture_json='{"status": "ok", "org_id": "x"}')
    assert out["verdict"]["status"] == "pass"          # без ValueError-краху
    assert out["verdict"]["http_status"] == 200        # загорнуто як 200-тіло


def test_simulate_fault_reproduces_failure(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    out = eng.simulate("whoami", fault="http_500")
    assert out["verdict"]["status"] == "fail"
    assert out["source_chain"][0] == "FaultSource(http_500)"


def test_simulate_without_substitution_warns_live_call(tmp_path: Path) -> None:
    # нема sim/фікстури/fault → підміни не було; note мусить чесно казати про живий виклик
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"org_id": "live"})

    eng = _engine(tmp_path, handler, adapter=_adapter(_feature(sim=None)))
    out = eng.simulate("whoami")
    assert seen == ["/api/v1/whoami"]      # запит реально пішов у gateway
    assert "ЖИВИЙ" in out["note"]          # і note цього не приховує


# --- dispatch (S4): coder/computer — ті самі важелі, апрув людський ---------------

def test_dispatch_fix_posts_task_with_failure_context(tmp_path: Path) -> None:
    cap: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/code/task":
            cap["body"] = json.loads(request.content)
            return httpx.Response(200, json={"reply": "план готовий", "target": "local"})
        return httpx.Response(404, json={})  # фіча падає → буде failure-вердикт

    eng = _engine(tmp_path, handler)
    eng.run()  # фіксуємо падіння whoami (404)
    out = eng.dispatch_fix("whoami", extra="після рестарту")
    body = cap["body"]
    assert body["target"] == "local"
    assert "whoami" in body["text"] and "GET /api/v1/whoami" in body["text"]
    assert "HTTP 404" in body["text"] and "після рестарту" in body["text"]
    assert "перевір deps.py" in body["text"]  # підказка адаптера доїхала
    assert out["ok"] is True and out["awaiting_confirm"] is False


def test_dispatch_fix_detects_confirm_marker(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "[[COMPUTER_CONFIRM:a1b2c3]] Очікую підтвердження"})

    eng = _engine(tmp_path, handler)
    out = eng.dispatch_fix("whoami")
    assert out["awaiting_confirm"] is True and out["confirm_code"] == "a1b2c3"
    assert "S4" in out["note"]


def test_verify_ui_and_screenshot_hit_driver_endpoints(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/v1/driver/screenshot":
            return httpx.Response(200, json={"text": "screen ok"})
        return httpx.Response(200, json={"reply": "[[COMPUTER_ADMIN_CONFIRM:z9]] admin"})

    eng = _engine(tmp_path, handler)
    v = eng.verify_ui("перевір вікно")
    assert v["confirm_code"] == "z9"  # ADMIN-варіант маркера теж ловиться
    s = eng.screenshot()
    assert s["ok"] is True and s["text"] == "screen ok"
    assert seen == ["/api/v1/driver/exec", "/api/v1/driver/screenshot"]


# --- loop_run: bounded test→fix→retest; S4 зупинка; ніколи не авто-апрув ----------

def _flaky_gateway(fix_after_dispatch: bool, confirm_in_reply: str = "") -> Callable[[httpx.Request], httpx.Response]:
    """Стан: whoami падає (500), поки не прилетить dispatch на /code/task — далі зелений."""
    state = {"fixed": False, "approvals": 0, "dispatches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/whoami":
            if state["fixed"]:
                return httpx.Response(200, json={"org_id": "org_x", "via": "basic"})
            return httpx.Response(500, json={"detail": "boom"})
        if path == "/api/v1/code/task":
            state["dispatches"] += 1
            if fix_after_dispatch:
                state["fixed"] = True
            reply = confirm_in_reply or "фікс застосовано"
            return httpx.Response(200, json={"reply": reply, "target": "local"})
        if path == "/api/v1/confirm/approve":
            state["approvals"] += 1
            return httpx.Response(200, json={"result": "ok"})
        return httpx.Response(200, json={})

    handler.state = state  # type: ignore[attr-defined]
    return handler


def test_loop_run_green_after_dispatch_and_retest(tmp_path: Path) -> None:
    handler = _flaky_gateway(fix_after_dispatch=True)
    eng = _engine(tmp_path, handler)
    out = eng.loop_run(feature="whoami")
    assert out["status"] == "green" and out["rounds"] == 2
    steps = [t["step"] for t in out["trace"]]
    assert steps == ["test", "dispatch:code", "test"]
    assert handler.state["approvals"] == 0  # S4: жодного авто-апруву


def test_loop_run_halts_awaiting_confirm_never_autoapproves(tmp_path: Path) -> None:
    handler = _flaky_gateway(fix_after_dispatch=True,
                             confirm_in_reply="[[COMPUTER_CONFIRM:q7]] Очікую підтвердження")
    eng = _engine(tmp_path, handler)
    out = eng.loop_run(feature="whoami")
    assert out["status"] == "awaiting_confirm" and out["confirm_code"] == "q7"
    assert handler.state["approvals"] == 0  # луп зупинився, апрув — за людиною (S4)
    assert "confirm_approve" in out["note"]


def test_loop_run_bounded_red_after_max_rounds(tmp_path: Path) -> None:
    handler = _flaky_gateway(fix_after_dispatch=False)  # фікс «не допомагає»
    eng = _engine(tmp_path, handler)
    out = eng.loop_run(feature="whoami", max_rounds=2)
    assert out["status"] == "red" and out["rounds"] == 2
    assert handler.state["dispatches"] == 2  # рівно по разу на раунд, без розгону


def test_loop_run_rejects_non_http_mode(tmp_path: Path) -> None:
    # у replay retest не бачить фікс, а dispatch бив би в живий gateway → fail-fast, нуль запитів
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("loop_run(mode='replay') не має чіпати мережу")

    eng = _engine(tmp_path, handler)
    with pytest.raises(server.ScenarioError, match="mode='http'"):
        eng.loop_run(feature="whoami", mode="replay")


def test_loop_run_nonpositive_max_rounds_falls_back_to_cfg(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    out = eng.loop_run(feature="whoami", max_rounds=-1)  # -1 не обходить стелю з конфігу
    assert out["status"] == "green" and out["rounds"] == 1


def test_loop_run_computer_dispatch_kind_uses_driver(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/v1/driver/status":
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"reply": "подивився"})

    feat = _feature("driver_status", path="/api/v1/driver/status", dispatch_kind="computer",
                    oracle={"ok_status": [200], "require_fields": ["enabled"],
                            "nonempty_fields": [], "forbid_fields": [], "latency_budget_ms": 0})
    eng = _engine(tmp_path, handler, adapter=_adapter(feat))
    eng.loop_run(feature="driver_status", max_rounds=1)
    assert "/api/v1/driver/exec" in seen  # ремедіація пішла у computer-use, не в coder


# --- порт audit: anti-leak (лише метадані) ----------------------------------------

def test_audit_never_leaks_response_values(tmp_path: Path) -> None:
    secret = "ДУЖЕ_СЕКРЕТНЕ_ЗНАЧЕННЯ_42"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"org_id": secret, "via": "basic"})

    p = tmp_path / "audit.jsonl"
    cfg = _cfg(tmp_path, AI_TESTER_AUDIT=str(p))
    http = server.GatewayHttp(cfg, transport=httpx.MockTransport(handler))  # реальний audit-sink
    eng = server.Engine(http, _adapter())  # реальний audit
    eng.run()
    blob = p.read_text(encoding="utf-8")
    assert "kind:ai_tester-run" in blob  # метадані є
    assert secret not in blob            # сирі значення — ні
    report_blob = (tmp_path / "artifacts" / "last_run.json").read_text(encoding="utf-8")
    assert secret not in report_blob     # і у звіті теж лише метадані


# --- adapter ↔ engine: реальний manifest не дрейфує --------------------------------

def test_real_manifest_loads_and_is_consistent() -> None:
    adp = server.Adapter.load()
    assert adp.profile == "jarvis"
    assert adp.base_url_default == server._DEFAULT_BASE_URL
    assert {"whoami", "chat", "code_task", "driver_exec"} <= set(adp.features)
    for feat in adp.features.values():
        assert feat.method in ("GET", "POST")
        assert feat.path.startswith("/api/v1/")
        assert feat.oracle.get("ok_status"), f"{feat.name}: oracle без ok_status"
        assert feat.dispatch_kind in ("code", "computer")
        if feat.gate_flag:
            assert feat.gated_statuses, f"{feat.name}: gate_flag без gated_statuses"
        if not feat.mutating:
            assert feat.sim is not None, f"{feat.name}: не-mutating фіча без sim-фікстури (replay)"


def test_real_manifest_mutating_features_marked() -> None:
    adp = server.Adapter.load()
    assert adp.features["code_task"].mutating is True
    assert adp.features["driver_exec"].mutating is True
    assert adp.features["whoami"].mutating is False


def test_real_manifest_gates_match_gateway_reality() -> None:
    # driver/code роути в gateway безумовні (driver.py / code.py target=local) — гейтів там нема
    adp = server.Adapter.load()
    gated = {n for n, f in adp.features.items() if f.gate_flag}
    assert gated == {"context_ingest", "context_search", "context_recent", "mcp_servers"}


# --- порт capabilities: FastMCP-wiring (skip без MCP-SDK) ---------------------------

def test_build_server_registers_tools(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import asyncio

    eng = _engine(tmp_path, _ok_handler)
    srv = server.build_server(engine=eng)
    tools = asyncio.run(srv.list_tools())
    assert sorted(t.name for t in tools) == [
        "confirm_approve", "confirm_cancel", "confirm_pending",
        "dispatch_fix", "features", "loop_run", "ready", "report",
        "run", "screenshot", "simulate", "verify_ui",
    ]


# --- redaction: SSOT-правила мають вантажитись і без jarvis_core на sys.path --------

def test_redactor_loads_ssot_rules_without_heavy_import() -> None:
    scrub = server._make_redactor()
    aws = "AKIAIOSFODNN7EXAMPLE"  # канонічний приклад AWS — ловить і SSOT, і fallback
    assert aws not in scrub(f"key {aws} here")
    # SSOT-специфічне правило `secret` (ghp_) — слабкий фолбек ловить лише sk-/pk-:
    # якщо редакція деградувала до фолбека, цей ассерт впаде (fake-токен, шлях tests/ у gitleaks-allowlist)
    gh = "ghp_abcdefghij1234567890"
    assert gh not in scrub(f"token {gh} here")


# --- readiness + report -------------------------------------------------------------

def test_ready_reports_gateway_and_features(tmp_path: Path) -> None:
    adp = _adapter(_feature(), _feature("code_task", mutating=True))
    eng = _engine(tmp_path, _ok_handler, adapter=adp)
    out = eng.ready()
    assert out["gateway"] is True and out["ready"] is True
    assert out["identity"]["org_id"] == "org_x"
    assert out["features_total"] == 2 and out["features_mutating"] == ["code_task"]


def test_ready_degrades_when_gateway_down(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нема з'єднання")

    eng = _engine(tmp_path, handler)
    out = eng.ready()
    assert out["gateway"] is False and out["ready"] is False
    assert "transport" in out["gateway_error"]


def test_report_falls_back_to_disk(tmp_path: Path) -> None:
    eng = _engine(tmp_path, _ok_handler)
    ran = eng.run()
    fresh = _engine(tmp_path, _ok_handler)  # новий процес: у памʼяті порожньо → диск
    assert fresh.report()["run_id"] == ran["run_id"]
    empty = _engine(tmp_path / "elsewhere", _ok_handler)
    assert "note" in empty.report()
