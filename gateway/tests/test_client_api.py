"""Client-API /api/v1/* — JWT login/refresh + unified whoami resolver (CL-1)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = ("admin", "secret")


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)


@pytest.fixture
def client_jwt(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-key-cl1-min-32-bytes-long-abcd")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_nojwt(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "jwt_secret", "")
    with TestClient(app) as c:
        yield c


# --- JWT за прапором (S2) ---

def test_login_disabled_without_secret(client_nojwt):
    r = client_nojwt.post("/api/v1/auth/login", json={"password": "secret"})
    assert r.status_code == 503


def test_whoami_basic_still_works_without_jwt(client_nojwt):
    # self-hosted без JWT: Basic-вхід у client-API працює (initData/Basic незмінні)
    r = client_nojwt.get("/api/v1/whoami", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["via"] == "basic"


# --- JWT login / refresh (CL-1.1) ---

def test_login_returns_token_pair(client_jwt):
    r = client_jwt.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"] and data["refresh_token"]
    assert data["expires_in"] == settings.jwt_access_ttl


def test_login_bad_password(client_jwt):
    assert client_jwt.post("/api/v1/auth/login", json={"password": "wrong"}).status_code == 401


def test_refresh_issues_new_access(client_jwt):
    refresh = client_jwt.post("/api/v1/auth/login", json={"password": "secret"}).json()["refresh_token"]
    r = client_jwt.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_refresh_rejects_access_token(client_jwt):
    # access-токен не можна використати як refresh (claim type mismatch)
    access = client_jwt.post("/api/v1/auth/login", json={"password": "secret"}).json()["access_token"]
    assert client_jwt.post("/api/v1/auth/refresh", json={"refresh_token": access}).status_code == 401


# --- unified resolver (CL-1.4): JWT / Basic / none ---

def test_whoami_via_jwt(client_jwt):
    tok = client_jwt.post("/api/v1/auth/login", json={"password": "secret"}).json()["access_token"]
    r = client_jwt.get("/api/v1/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    d = r.json()
    assert d["via"] == "jwt"
    assert d["role"] == "owner"
    assert d["plan"] == "studio"
    assert d["org_id"] == "00000000-0000-0000-0000-000000000001"
    assert d["legacy_uid"] == 42
    # plan limits surfaced (AP-4.3): studio = self-hosted owner → усі стелі null (UNLIMITED)
    assert d["limits"] == {
        "requests_per_day": None,
        "tokens_per_month": None,
        "max_api_keys": None,
        "rate_limit_per_min": None,
    }


def test_whoami_via_basic(client_jwt):
    r = client_jwt.get("/api/v1/whoami", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["via"] == "basic"


def test_whoami_requires_auth(client_jwt):
    assert client_jwt.get("/api/v1/whoami").status_code == 401


def test_whoami_invalid_jwt_falls_through_to_401(client_jwt):
    r = client_jwt.get("/api/v1/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


# --- robustness: малформ ПІДПИСАНОГО токена → 401, не 500 (security review CL-1) ---

def test_refresh_malformed_sub_returns_401_not_500(client_jwt):
    import jwt as _jwt

    # валідний підпис, але нечисловий sub → int(sub) не має валити процес
    bad = _jwt.encode({"sub": "not-a-number", "type": "refresh"}, settings.jwt_secret, algorithm="HS256")
    assert client_jwt.post("/api/v1/auth/refresh", json={"refresh_token": bad}).status_code == 401


def test_whoami_token_missing_sub_returns_401(client_jwt):
    import jwt as _jwt

    bad = _jwt.encode({"type": "access", "org": "x"}, settings.jwt_secret, algorithm="HS256")
    r = client_jwt.get("/api/v1/whoami", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


# --- /api/v1/chat (CL-3.3 backend) — reuse агент-шляху через unified resolver ---

def test_chat_via_basic_reuses_agent(client_jwt):
    client_jwt.app.state.tools.process = AsyncMock(return_value="привіт від агента")
    r = client_jwt.post("/api/v1/chat", auth=AUTH, json={"text": "як справи?"})
    assert r.status_code == 200
    d = r.json()
    assert d["reply"] == "привіт від агента"
    assert d["via"] == "basic"
    # агент викликаний із числовим uid (legacy_uid=42) і текстом
    payload = client_jwt.app.state.tools.process.await_args.args[0]
    assert payload["user_id"] == 42 and payload["text"] == "як справи?"


def test_chat_via_jwt(client_jwt):
    client_jwt.app.state.tools.process = AsyncMock(return_value="ok")
    tok = client_jwt.post("/api/v1/auth/login", json={"password": "secret"}).json()["access_token"]
    r = client_jwt.post("/api/v1/chat", headers={"Authorization": f"Bearer {tok}"}, json={"text": "hi"})
    assert r.status_code == 200
    assert r.json()["via"] == "jwt"


def test_chat_requires_auth(client_jwt):
    assert client_jwt.post("/api/v1/chat", json={"text": "hi"}).status_code == 401


def test_chat_empty_text_400(client_jwt):
    client_jwt.app.state.tools.process = AsyncMock(return_value="x")
    assert client_jwt.post("/api/v1/chat", auth=AUTH, json={"text": "  "}).status_code == 400


def test_chat_rejects_unknown_mode(client_jwt):
    # fail-fast (P2): невалідний mode → 400 на вході, як у сусідніх agent-entry
    client_jwt.app.state.tools.process = AsyncMock(return_value="x")
    r = client_jwt.post("/api/v1/chat", auth=AUTH, json={"text": "hi", "mode": "garbage"})
    assert r.status_code == 400


def test_chat_normalizes_valid_mode(client_jwt):
    client_jwt.app.state.tools.process = AsyncMock(return_value="ok")
    r = client_jwt.post("/api/v1/chat", auth=AUTH, json={"text": "hi", "mode": "AGENT"})
    assert r.status_code == 200
    assert r.json()["mode"] == "agent"  # lower+strip нормалізація через require_mode
    assert client_jwt.app.state.tools.process.await_args.args[0]["mode"] == "agent"
