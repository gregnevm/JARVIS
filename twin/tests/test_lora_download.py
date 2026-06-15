"""Twin LoRA file download for Edge sync."""
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.config import settings


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "registry_db", str(tmp_path / "reg.db"))
    return TestClient(main.app)


def test_download_active_lora(tmp_path: Path, monkeypatch):
    lora = tmp_path / "twin" / "lora" / "v1.gguf"
    lora.parent.mkdir(parents=True)
    lora.write_bytes(b"GGUF_DATA")
    with _client(tmp_path, monkeypatch) as c:
        c.post("/registry/lora", json={"version": "v1", "path": "v1.gguf"})
        c.post("/registry/lora/v1/promote")
        r = c.get("/registry/lora/active/download")
        assert r.status_code == 200
        assert r.content == b"GGUF_DATA"


def test_download_no_active(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/registry/lora/active/download").status_code == 404
