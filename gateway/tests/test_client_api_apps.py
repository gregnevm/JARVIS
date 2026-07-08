"""APK-apps: upsert web-бандл, список, bundle (in-app update), видалення."""
from __future__ import annotations

import pytest
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

AUTH = ("admin", "secret")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "platform_password", "secret")
    monkeypatch.setattr(settings, "admin_panel_user", "admin")
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "access_store_path", str(tmp_path / "users.json"))
    monkeypatch.setattr(settings, "health_watch_interval", 0.0)
    monkeypatch.setattr(settings, "jwt_secret", "")
    with TestClient(app) as c:
        yield c


def test_upsert_list_bundle_cycle(client):
    r = client.post("/api/v1/apps/snake", auth=AUTH,
                    json={"name": "Snake", "html": "<h1>Game</h1>"})
    assert r.status_code == 200 and r.json()["version"] == "1"
    # список
    lst = client.get("/api/v1/apps", auth=AUTH).json()["apps"]
    assert any(a["id"] == "snake" and a["name"] == "Snake" for a in lst)
    # bundle (те, що рендерить WebView)
    b = client.get("/api/v1/apps/snake/bundle", auth=AUTH)
    assert b.status_code == 200 and "<h1>Game</h1>" in b.text
    assert b.headers["cache-control"] == "no-store"  # завжди свіже → in-app update


def test_upsert_autoincrements_version(client):
    client.post("/api/v1/apps/tool", auth=AUTH, json={"name": "T", "html": "v1"})
    r = client.post("/api/v1/apps/tool", auth=AUTH, json={"name": "T", "html": "v2"})
    assert r.json()["version"] == "2"  # авто-інкремент = оновлення без перевстановлення APK
    assert "v2" in client.get("/api/v1/apps/tool/bundle", auth=AUTH).text


def test_upsert_preserves_nonnumeric_version(client):
    # semver-версія задана явно, далі оновлення без версії → НЕ скидається на "1"
    client.post("/api/v1/apps/semv", auth=AUTH,
                json={"name": "S", "html": "v1", "version": "1.2.0"})
    r = client.post("/api/v1/apps/semv", auth=AUTH, json={"name": "S", "html": "v2"})
    assert r.json()["version"] == "1.2.0"


def test_upsert_rejects_oversized_bundle(client, monkeypatch):
    from app.client_api import apps
    monkeypatch.setattr(apps, "_MAX_BUNDLE_BYTES", 8)
    r = client.post("/api/v1/apps/big", auth=AUTH,
                    json={"name": "B", "html": "x" * 9})
    assert r.status_code == 413
    # межа рівно на стелі — ок
    assert client.post("/api/v1/apps/big", auth=AUTH,
                       json={"name": "B", "html": "x" * 8}).status_code == 200


def test_upsert_rejects_blank_or_long_name(client, monkeypatch):
    from app.client_api import apps
    assert client.post("/api/v1/apps/n1", auth=AUTH,
                       json={"name": "  ", "html": "y"}).status_code == 400
    monkeypatch.setattr(apps, "_MAX_NAME_LEN", 4)
    assert client.post("/api/v1/apps/n2", auth=AUTH,
                       json={"name": "toolong", "html": "y"}).status_code == 400


def test_upsert_app_count_cap(client, monkeypatch):
    from app.client_api import apps
    monkeypatch.setattr(apps, "_MAX_APPS_PER_USER", 2)
    assert client.post("/api/v1/apps/a1", auth=AUTH, json={"name": "A", "html": "y"}).status_code == 200
    assert client.post("/api/v1/apps/a2", auth=AUTH, json={"name": "A", "html": "y"}).status_code == 200
    # 3-тя НОВА апка → 409
    assert client.post("/api/v1/apps/a3", auth=AUTH, json={"name": "A", "html": "y"}).status_code == 409
    # оновлення НАЯВНОЇ (не росте кількість) — досі дозволено
    assert client.post("/api/v1/apps/a1", auth=AUTH, json={"name": "A", "html": "y2"}).status_code == 200


def test_invalid_id_400(client):
    assert client.post("/api/v1/apps/Bad ID!", auth=AUTH,
                       json={"name": "x", "html": "y"}).status_code == 400


def test_missing_app_404(client):
    assert client.get("/api/v1/apps/nope/bundle", auth=AUTH).status_code == 404


def test_delete(client):
    client.post("/api/v1/apps/temp", auth=AUTH, json={"name": "T", "html": "z"})
    assert client.delete("/api/v1/apps/temp", auth=AUTH).json()["ok"] is True
    assert client.get("/api/v1/apps/temp/bundle", auth=AUTH).status_code == 404


def test_requires_auth(client):
    assert client.get("/api/v1/apps").status_code == 401
