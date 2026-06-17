"""`/connect/<token>` — Telegram one-tap → JWT-cookie → авторизована веб-сесія."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import auth_links
from app.config import settings
from app.main import app
from app.saas import auth as jwt_auth


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, k, ttl, v):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    async def aclose(self):
        return None


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-key-connect-min-32-bytes-aaaa")


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    with TestClient(app) as c:
        app.state.redis = FakeRedis()
        yield c


def _seed(token: str, uid: int = 42, target: str = "web") -> str:
    """Кладе connect-токен прямо в FakeRedis (формат `uid:target` за `auth_links._key`)."""
    app.state.redis.store[auth_links._key(token)] = f"{uid}:{target}"
    return token


def test_connect_sets_cookie_and_redirects(client):
    _seed("tok-web")
    r = client.get("/connect/tok-web", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/platform"
    assert jwt_auth.JWT_COOKIE in r.cookies
    claims = jwt_auth.decode(r.cookies[jwt_auth.JWT_COOKIE])
    assert claims["legacy_uid"] == 42


def test_connect_json_format_returns_tokens(client):
    _seed("tok-json")
    r = client.get("/connect/tok-json?format=json")
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["token_type"] == "bearer"


def test_connect_token_is_one_time(client):
    _seed("tok-once")
    assert client.get("/connect/tok-once", follow_redirects=False).status_code == 303
    assert client.get("/connect/tok-once", follow_redirects=False).status_code == 401


def test_connect_unknown_token_401(client):
    assert client.get("/connect/missing", follow_redirects=False).status_code == 401


def test_connect_respects_safe_next(client):
    _seed("tok-next")
    r = client.get("/connect/tok-next?next=/app", follow_redirects=False)
    assert r.headers["location"] == "/app"
    _seed("tok-evil")
    r2 = client.get("/connect/tok-evil?next=https://evil.com", follow_redirects=False)
    assert r2.headers["location"] == "/platform"


def test_connect_denies_non_whitelisted(client):
    _seed("tok-bad", uid=999)
    assert client.get("/connect/tok-bad", follow_redirects=False).status_code == 403


def test_cookie_authorizes_platform_whoami(client):
    _seed("tok-p")
    access = client.get("/connect/tok-p?format=json").json()["access_token"]
    r = client.get("/platform/api/whoami", cookies={jwt_auth.JWT_COOKIE: access})
    assert r.status_code == 200
    body = r.json()
    assert body["via"] == "cookie"
    assert body["user_id"] == 42


def test_cookie_authorizes_client_whoami(client):
    _seed("tok-c")
    access = client.get("/connect/tok-c?format=json").json()["access_token"]
    r = client.get("/api/v1/whoami", cookies={jwt_auth.JWT_COOKIE: access})
    assert r.status_code == 200
    assert r.json()["via"] == "jwt"


def test_connect_503_without_jwt(client, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    _seed("tok-nojwt")
    assert client.get("/connect/tok-nojwt", follow_redirects=False).status_code == 503
