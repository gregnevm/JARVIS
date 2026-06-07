"""SyncAgent — push context delta → Twin, pull active LoRA (DESIGN §7.3)."""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from mode_detect import ConnectMode, detect_mode

logger = logging.getLogger("jarvis.edge.sync")


_EDGE_DIR = Path(__file__).resolve().parent
if str(_EDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_DIR))


@dataclass
class EdgeConfig:
    edge_id: str = "usb_01"
    twin_url: str = "http://127.0.0.1:8765"
    kobold_host: str = "http://127.0.0.1:5001"
    context_log: str = "data/context_log.jsonl"
    lora_dir: str = "lora/versioned"
    lora_active_link: str = "lora/active/jarvis.gguf"
    sync_state: str = "data/sync_state.json"
    vpn_hosts: tuple[str, ...] = ()
    sync_interval_sec: int = 300
    memory_url: str = ""  # LAN: http://host:8100 для /embed у RAG

    @classmethod
    def load(cls, path: Path) -> EdgeConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        vpn = raw.get("vpn_hosts") or []
        return cls(
            edge_id=str(raw.get("edge_id", cls.edge_id)),
            twin_url=str(raw.get("twin_url", cls.twin_url)),
            kobold_host=str(raw.get("kobold_host", cls.kobold_host)),
            context_log=str(raw.get("context_log", cls.context_log)),
            lora_dir=str(raw.get("lora_dir", cls.lora_dir)),
            lora_active_link=str(raw.get("lora_active_link", cls.lora_active_link)),
            sync_state=str(raw.get("sync_state", cls.sync_state)),
            vpn_hosts=tuple(str(h) for h in vpn),
            sync_interval_sec=int(raw.get("sync_interval_sec", cls.sync_interval_sec)),
            memory_url=str(raw.get("memory_url", cls.memory_url or "")),
        )


@dataclass
class SyncState:
    last_pushed_idx: int = 0
    active_lora_version: str | None = None

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            last_pushed_idx=int(data.get("last_pushed_idx", 0)),
            active_lora_version=data.get("active_lora_version"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "last_pushed_idx": self.last_pushed_idx,
                    "active_lora_version": self.active_lora_version,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class SyncAgent:
    def __init__(self, root: Path, cfg: EdgeConfig, client: httpx.Client | None = None) -> None:
        self.root = root
        self.cfg = cfg
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._state_path = root / cfg.sync_state
        self.state = SyncState.load(self._state_path)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def mode(self) -> ConnectMode:
        return detect_mode(self.cfg.twin_url, vpn_hosts=self.cfg.vpn_hosts)

    def _read_log_lines(self) -> list[str]:
        log_path = self.root / self.cfg.context_log
        if not log_path.is_file():
            return []
        return [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def push_logs(self) -> dict[str, Any]:
        lines = self._read_log_lines()
        start = self.state.last_pushed_idx
        delta = lines[start:]
        if not delta:
            return {"pushed": 0, "mode": self.mode()}
        if self.mode() == "OFFLINE":
            return {"pushed": 0, "skipped": "offline", "pending": len(delta)}
        logs = [json.loads(ln) for ln in delta]
        resp = self._client.post(
            f"{self.cfg.twin_url.rstrip('/')}/ingest/logs",
            json={
                "edge_id": self.cfg.edge_id,
                "delta_start_idx": start,
                "logs": logs,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self.state.last_pushed_idx = start + len(delta)
        self.state.save(self._state_path)
        return {"pushed": len(delta), "twin": body, "mode": self.mode()}

    def pull_lora(self) -> dict[str, Any]:
        if self.mode() == "OFFLINE":
            return {"pulled": False, "skipped": "offline"}
        meta_resp = self._client.get(f"{self.cfg.twin_url.rstrip('/')}/latest/lora")
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        version = meta.get("version")
        if not version:
            return {"pulled": False, "reason": "no active lora"}
        if version == self.state.active_lora_version:
            return {"pulled": False, "reason": "up to date", "version": version}
        dl = self._client.get(
            f"{self.cfg.twin_url.rstrip('/')}/registry/lora/active/download"
        )
        if dl.status_code == 404:
            return {"pulled": False, "reason": "file missing on twin", "version": version}
        dl.raise_for_status()
        lora_dir = self.root / self.cfg.lora_dir
        lora_dir.mkdir(parents=True, exist_ok=True)
        dest = lora_dir / f"jarvis_{version}.gguf"
        dest.write_bytes(dl.content)
        active = self.root / self.cfg.lora_active_link
        active.parent.mkdir(parents=True, exist_ok=True)
        if active.exists() or active.is_symlink():
            active.unlink()
        try:
            active.symlink_to(dest.resolve())
        except OSError:
            # Windows USB без symlink — копія
            active.write_bytes(dest.read_bytes())
        self.state.active_lora_version = str(version)
        self.state.save(self._state_path)
        return {"pulled": True, "version": version, "path": str(dest)}

    def run_once(self) -> dict[str, Any]:
        mode = self.mode()
        out: dict[str, Any] = {"mode": mode, "edge_id": self.cfg.edge_id}
        out["push"] = self.push_logs()
        out["pull"] = self.pull_lora()
        return out

    def run_loop(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        logger.info("SyncAgent edge_id=%s twin=%s", self.cfg.edge_id, self.cfg.twin_url)
        while True:
            try:
                result = self.run_once()
                logger.info("sync: %s", json.dumps(result, ensure_ascii=False))
            except httpx.HTTPError as exc:
                logger.warning("sync failed: %s", exc)
            time.sleep(max(30, self.cfg.sync_interval_sec))


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="JARVIS Edge SyncAgent")
    p.add_argument("--root", default=str(Path(__file__).resolve().parent))
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--once", action="store_true")
    p.add_argument("--loop", action="store_true")
    args = p.parse_args()

    root = Path(args.root)
    cfg_path = root / args.config
    if not cfg_path.is_file():
        print(f"Missing {cfg_path} — copy config.yaml.example", file=sys.stderr)
        return 1
    cfg = EdgeConfig.load(cfg_path)
    agent = SyncAgent(root, cfg)
    try:
        if args.loop:
            agent.run_loop()
            return 0
        print(json.dumps(agent.run_once(), indent=2, ensure_ascii=False))
        return 0
    finally:
        agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
