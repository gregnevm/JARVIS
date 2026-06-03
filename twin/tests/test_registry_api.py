"""ModelRegistry REST — /registry/* (FastAPI TestClient)."""
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.config import settings


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "registry_db", str(tmp_path / "reg.db"))
    return TestClient(main.app)


def test_register_and_list(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post(
            "/registry/lora",
            json={"version": "v1", "path": "/lora/v1.gguf", "eval_score": 0.85},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "candidate"
        versions = c.get("/registry/versions").json()["versions"]
        assert len(versions) == 1


def test_promote_and_latest(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/registry/lora", json={"version": "v1", "path": "/lora/v1.gguf"})
        c.post("/registry/lora/v1/promote")
        assert c.get("/latest/lora").json()["version"] == "v1"


def test_rollback(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/registry/lora", json={"version": "v1", "path": "/a"})
        c.post("/registry/lora", json={"version": "v2", "path": "/b"})
        c.post("/registry/lora/v1/promote")
        c.post("/registry/lora/v2/promote")
        r = c.post("/registry/lora/rollback?n=1")
        assert r.status_code == 200
        assert r.json()["version"] == "v1"


def test_promote_unknown_404(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.post("/registry/lora/nope/promote").status_code == 404
