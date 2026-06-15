"""Edge SyncAgent — push/pull з mock Twin."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

EDGE = Path(__file__).resolve().parents[1]
if str(EDGE) not in sys.path:
    sys.path.insert(0, str(EDGE))

from edge_sync import EdgeConfig, SyncAgent  # noqa: E402


def test_push_logs_offline_skips(tmp_path: Path):
    cfg = EdgeConfig(
        edge_id="t1",
        twin_url="http://127.0.0.1:1",
        context_log="data/context_log.jsonl",
        sync_state="data/sync_state.json",
    )
    log = tmp_path / "data" / "context_log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"event": "chat"}) + "\n", encoding="utf-8")
    agent = SyncAgent(tmp_path, cfg, client=httpx.Client(timeout=0.5))
    try:
        out = agent.push_logs()
        assert out["pushed"] == 0
        assert out["skipped"] == "offline"
        assert agent.state.last_pushed_idx == 0
    finally:
        agent.close()


def test_pull_lora_downloads(tmp_path: Path, monkeypatch):
    lora_bytes = b"GGUF_FAKE"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/latest/lora":
            return httpx.Response(200, json={"version": "v1", "path": "v1.gguf"})
        if request.url.path == "/registry/lora/active/download":
            return httpx.Response(200, content=lora_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://twin.test")

    cfg = EdgeConfig(
        edge_id="t1",
        twin_url="http://twin.test",
        lora_dir="lora/versioned",
        lora_active_link="lora/active/jarvis.gguf",
        sync_state="data/sync_state.json",
    )
    agent = SyncAgent(tmp_path, cfg, client=client)
    monkeypatch.setattr(agent, "mode", lambda: "LAN")
    try:
        out = agent.pull_lora()
        assert out["pulled"] is True
        assert (tmp_path / "lora" / "versioned" / "jarvis_v1.gguf").exists()
        assert agent.state.active_lora_version == "v1"
    finally:
        agent.close()
