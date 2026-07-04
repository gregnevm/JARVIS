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


def test_download_rejects_path_escaping_data_dir(tmp_path: Path, monkeypatch):
    # End-to-end: клієнт реєструє LoRA з абсолютним шляхом ПОЗА data_dir
    # (arbitrary-file-read), промоутить → download мусить дати 404, не байти секрету.
    (tmp_path / "twin" / "lora").mkdir(parents=True)
    secret = tmp_path.parent / f"leak_{tmp_path.name}.txt"
    secret.write_text("TOPSECRET")
    try:
        with _client(tmp_path, monkeypatch) as c:
            c.post("/registry/lora", json={"version": "evil", "path": str(secret)})
            c.post("/registry/lora/evil/promote")
            r = c.get("/registry/lora/active/download")
            assert r.status_code == 404
            assert b"TOPSECRET" not in r.content
    finally:
        secret.unlink(missing_ok=True)
