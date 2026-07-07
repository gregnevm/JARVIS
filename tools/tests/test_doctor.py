"""jarvis doctor: health-чеки, sandbox/env-логіка критичності, summarize/exit."""
from __future__ import annotations

import httpx
from app import doctor
from app.config import settings


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_check_service_ok_and_down():
    ok = doctor.check_service("memory", "http://memory:8100", critical=True,
                              client=_client(lambda r: httpx.Response(200)))
    assert ok["ok"] and ok["name"] == "service:memory"

    def _boom(request):
        raise httpx.ConnectError("refused", request=request)

    down = doctor.check_service("twin", "http://twin:8765", critical=False,
                                client=_client(_boom))
    assert not down["ok"] and down["critical"] is False


def test_check_ollama(monkeypatch):
    monkeypatch.setattr(settings, "ollama_host", "http://host:11434")
    res = doctor.check_ollama(_client(lambda r: httpx.Response(200)))
    assert res["ok"] and "11434" in str(res["detail"])


def test_check_sandbox_present():
    res = doctor.check_sandbox(which=lambda x: "/usr/bin/bwrap")
    assert res["ok"] and "є" in str(res["detail"])


def test_check_sandbox_missing_strict_is_critical(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", True)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", True)
    res = doctor.check_sandbox(which=lambda x: None)
    assert res["critical"] is True and res["ok"] is False


def test_check_sandbox_missing_but_not_strict_ok(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_exec", False)
    res = doctor.check_sandbox(which=lambda x: None)
    assert res["ok"] is True and res["critical"] is False


def test_check_env_presence(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "abc")
    out = doctor.check_env(("admin_user_ids",))
    assert out[0]["ok"] is True
    monkeypatch.setattr(settings, "admin_user_ids", "")
    out = doctor.check_env(("admin_user_ids",))
    assert out[0]["ok"] is False


def test_run_doctor_all_green(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "tok")
    monkeypatch.setattr(settings, "enable_code_exec", False)
    results = doctor.run_doctor(
        client=_client(lambda r: httpx.Response(200)),
        which=lambda x: "/usr/bin/bwrap",
    )
    healthy, report = doctor.summarize(results)
    assert healthy and "UNHEALTHY" not in report


def test_run_doctor_unhealthy_when_critical_service_down(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "tok")

    def handler(request: httpx.Request) -> httpx.Response:
        if "memory" in request.url.host:      # критичний сервіс лежить
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200)

    results = doctor.run_doctor(client=_client(handler), which=lambda x: "/usr/bin/bwrap")
    healthy, report = doctor.summarize(results)
    assert not healthy and "UNHEALTHY" in report


def test_run_doctor_noncritical_down_stays_healthy(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "tok")
    monkeypatch.setattr(settings, "enable_code_exec", False)

    def handler(request: httpx.Request) -> httpx.Response:
        if "twin" in request.url.host:        # некритичний — не валить
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200)

    results = doctor.run_doctor(client=_client(handler), which=lambda x: "/usr/bin/bwrap")
    healthy, _ = doctor.summarize(results)
    assert healthy


def test_main_json_and_exit(monkeypatch, capsys):
    monkeypatch.setattr(settings, "admin_user_ids", "")
    monkeypatch.setattr(doctor, "run_doctor", lambda **k: [
        {"name": "env:x", "ok": False, "critical": True, "detail": "порожнє"},
    ])
    rc = doctor.main(["--json"])
    assert rc == 1
    assert '"ok": false' in capsys.readouterr().out
