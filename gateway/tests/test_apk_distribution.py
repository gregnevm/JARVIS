"""BE4 — web-роздача APK (/platform/apk*) + пейринг (mint у platform, redeem у client-api)."""
from __future__ import annotations

from pathlib import Path

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

AUTH = ("admin", "secret")
_REAL_APK = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "jarvis-mvp.apk"


def _base(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-key-cl1-min-32-bytes-long-abcd")


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, k):
        self.store.pop(k, None)

    async def aclose(self):
        return None


@pytest.fixture
def client(monkeypatch, tmp_path):
    _base(monkeypatch, tmp_path)
    # Вказуємо на реальний зібраний APK (інакше info=available:false).
    monkeypatch.setattr(settings, "apk_artifact_path", str(_REAL_APK))
    with TestClient(app) as c:
        app.state.redis = FakeRedis()  # без реального redis
        yield c


@pytest.mark.skipif(not _REAL_APK.is_file(), reason="APK не зібрано (mobile/build-apk.ps1)")
def test_apk_info_available(client):
    r = client.get("/platform/api/apk/info", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is True
    assert d["version"] and d["sha256"]


@pytest.mark.skipif(not _REAL_APK.is_file(), reason="APK не зібрано")
def test_apk_download(client):
    r = client.get("/platform/apk", auth=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.android.package-archive")
    assert len(r.content) > 1000


def test_apk_download_requires_auth(client):
    assert client.get("/platform/apk").status_code == 401


def test_pair_mint_then_redeem(client):
    # mint (штаб) → deeplink+token
    r = client.post("/platform/api/apk/pair", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["deeplink"].startswith("jarvis://pair?")
    token = body["token"]
    # redeem (APK) → JWT-пара, токен одноразовий
    r2 = client.post("/api/v1/auth/pair", json={"token": token})
    assert r2.status_code == 200
    assert r2.json()["access_token"]
    # повторний redeem → 401 (one-time)
    assert client.post("/api/v1/auth/pair", json={"token": token}).status_code == 401


def test_pair_redeem_invalid_token(client):
    assert client.post("/api/v1/auth/pair", json={"token": "nope"}).status_code == 401
