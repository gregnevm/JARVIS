"""train_unsloth.py — ShareGPT validation + dry-run (без GPU/unsloth)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "runpod" / "train_unsloth.py"


def _run(args: list[str], *, cwd: Path, data: str) -> subprocess.CompletedProcess[str]:
    train = cwd / "train.jsonl"
    train.write_text(data, encoding="utf-8")
    cmd = [sys.executable, str(SCRIPT), "--data-dir", str(cwd), "--output-dir", str(cwd / "out")]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))


def test_dry_run_valid_sharegpt(tmp_path: Path):
    row = {
        "conversations": [
            {"from": "human", "value": "hello"},
            {"from": "gpt", "value": "hi"},
        ]
    }
    proc = _run(["--dry-run"], cwd=tmp_path, data=json.dumps(row) + "\n")
    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "out" / "train_meta.json").read_text(encoding="utf-8"))
    assert meta["samples_valid"] == 1


def test_dry_run_rejects_empty_conversations(tmp_path: Path):
    row = {"conversations": [{"from": "human", "value": "solo"}]}
    proc = _run(["--dry-run"], cwd=tmp_path, data=json.dumps(row) + "\n")
    assert proc.returncode == 1
    meta = json.loads((tmp_path / "out" / "train_meta.json").read_text(encoding="utf-8"))
    assert meta["samples_valid"] == 0


def test_missing_train_file(tmp_path: Path):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--data-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 1
