"""SyncServer API — /ingest/logs, /latest/lora, /status (FastAPI TestClient)."""
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.config import settings


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "registry_db", str(tmp_path / "reg.db"))
    return TestClient(main.app)


def test_health(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_ingest_increments_last_idx(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r1 = c.post("/ingest/logs", json={"edge_id": "usb_01", "logs": [{"s": 1}, {"s": 2}]})
        assert r1.json() == {"accepted": 2, "last_idx": 2}
        r2 = c.post("/ingest/logs", json={"edge_id": "usb_01", "logs": [{"s": 3}]})
        assert r2.json() == {"accepted": 1, "last_idx": 3}


def test_ingest_isolated_per_edge(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/ingest/logs", json={"edge_id": "a", "logs": [{"s": 1}]})
        r = c.post("/ingest/logs", json={"edge_id": "b", "logs": [{"s": 1}]})
        assert r.json()["last_idx"] == 1  # лог "b" окремий від "a"


def test_latest_lora_empty(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/latest/lora").json() == {"version": None}


def test_latest_lora_after_promote(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        main.app.state.registry.register_lora("v1", "/lora/v1.gguf", eval_score=0.9)
        main.app.state.registry.promote("v1")
        body = c.get("/latest/lora").json()
        assert body["version"] == "v1"
        assert body["eval_score"] == 0.9
        assert body["path"] == "/lora/v1.gguf"


def test_status_reports_edges(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/ingest/logs", json={"edge_id": "usb_01", "logs": [{"s": 1}, {"s": 2}]})
        body = c.get("/status").json()
        assert body["edges"]["usb_01"] == 2
        assert body["active_lora"] is None
