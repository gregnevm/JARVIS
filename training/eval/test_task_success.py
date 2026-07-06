"""task_success: сценарії валідні, чеки коректні, gate-семантика, mock-транспорт."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import task_success  # noqa: E402


def test_scenarios_file_valid():
    scenarios = task_success.load_scenarios()
    assert len(scenarios) >= 20
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids)), "id сценаріїв мають бути унікальні"
    for sc in scenarios:
        assert sc["category"] in {"health", "tools", "security", "authority", "ops"}
        assert sc["request"]["service"] in {"tools", "gateway", "memory", "twin"}
        for expect in sc["expect"]:
            assert expect["type"] in {"status", "json_key", "contains_any"}


def _resp(status: int = 200, body: dict | str = "") -> httpx.Response:
    if isinstance(body, dict):
        return httpx.Response(status, json=body, request=httpx.Request("GET", "http://t/"))
    return httpx.Response(status, text=body, request=httpx.Request("GET", "http://t/"))


def test_check_status():
    ok, _ = task_success.check({"type": "status", "code": 200}, _resp(200))
    assert ok
    ok, reason = task_success.check({"type": "status", "code": 200}, _resp(503))
    assert not ok and "503" in reason


def test_check_json_key():
    ok, _ = task_success.check({"type": "json_key", "key": "approval_policy"}, _resp(200, {"approval_policy": "smart"}))
    assert ok
    ok, _ = task_success.check({"type": "json_key", "key": "missing"}, _resp(200, {"a": 1}))
    assert not ok


def test_check_contains_any_field_and_wildcard():
    resp = _resp(200, {"result": "Код відхилено guard-правилом (deny:env-exfiltration)."})
    ok, reason = task_success.check(
        {"type": "contains_any", "field": "result", "any": ["відхилено guard-правилом", "вимкнено"]}, resp
    )
    assert ok and "відхилено" in reason
    ok, _ = task_success.check({"type": "contains_any", "field": "*", "any": ["deny:env"]}, resp)
    assert ok
    ok, _ = task_success.check({"type": "contains_any", "field": "result", "any": ["немає такого"]}, resp)
    assert not ok


def test_check_unknown_type_fails_closed():
    ok, reason = task_success.check({"type": "telepathy"}, _resp(200))
    assert not ok and "fail-closed" in reason


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_run_all_end_to_end_with_mock_stack():
    """Повний прогін 20+ сценаріїв проти мок-стека, що імітує живі контракти."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/calc":
            expr = json.loads(request.content)["expression"]
            if expr == "17*23":
                return httpx.Response(200, json={"result": "391"})
            if len(expr) > 500:
                return httpx.Response(200, json={"result": "Завеликий вираз."})
            return httpx.Response(200, json={"result": "Помилка обчислення: syntax"})
        if path == "/tool/dispatch":
            return httpx.Response(200, json={"text": "42"})
        if path == "/parse_file":
            return httpx.Response(200, json={"text": "Файл не знайдено: /nonexistent/task_success_probe.txt"})
        if path == "/code_exec":
            code = json.loads(request.content)["code"]
            if "os.environ" in code or "subprocess" in code:
                return httpx.Response(200, json={"result": "Код відхилено guard-правилом (deny:x)."})
            return httpx.Response(200, json={"result": "4"})
        if path == "/computer/powershell/policy":
            return httpx.Response(200, json={"approval_policy": "(flags)", "require_confirm": True})
        return httpx.Response(200, json={"ok": True})

    results = task_success.run_all(task_success.load_scenarios(), client=_mock_client(handler))
    pct, report = task_success.summarize(results)
    failed = [r for r in results if not r["ok"]]
    assert not failed, f"впали: {failed}\n{report}"
    assert pct == 100.0
    assert all(r["latency_ms"] is not None for r in results)


def test_run_all_gate_detects_regression():
    """Регресія контракту (guard зник) → сценарій падає, pct < 100."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/code_exec":
            # guard «зламався»: секрети витекли замість відмови
            return httpx.Response(200, json={"result": "environ({'API_KEY': 'leak'})"})
        return httpx.Response(200, json={"result": "", "text": "", "ok": True})

    scenarios = [s for s in task_success.load_scenarios() if s["category"] == "security"]
    results = task_success.run_all(scenarios, client=_mock_client(handler))
    assert any(not r["ok"] for r in results)
    pct, _ = task_success.summarize(results)
    assert pct < 100.0


def test_run_all_only_filter_and_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    results = task_success.run_all(task_success.load_scenarios(), client=_mock_client(handler), only="health")
    assert results and all(r["latency_ms"] is None and not r["ok"] for r in results)
    assert all("HTTP" in r["reason"] for r in results)


def test_summarize_empty():
    pct, report = task_success.summarize([])
    assert pct == 0.0 and "0/0" in report
