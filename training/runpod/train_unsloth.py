#!/usr/bin/env python3
"""D.1 — Unsloth QLoRA skeleton (RunPod). Розширити після підключення GPU burst."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="JARVIS LoRA train (Unsloth skeleton)")
    p.add_argument("--data-dir", default="/workspace/data")
    p.add_argument("--output-dir", default="/workspace/output/lora")
    p.add_argument("--base-model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit")
    p.add_argument("--train-file", default="train.jsonl")
    p.add_argument("--max-steps", type=int, default=200)
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    train_path = data_dir / args.train_file
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not train_path.is_file():
        print(f"Missing train file: {train_path}", file=sys.stderr)
        return 1

    lines = [ln for ln in train_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"Train samples: {len(lines)} base={args.base_model} steps={args.max_steps}")

    try:
        import unsloth  # noqa: F401
    except ImportError:
        print(
            "unsloth not installed. On RunPod: pip install unsloth && see training/README.md",
            file=sys.stderr,
        )
        meta = {
            "status": "skeleton",
            "samples": len(lines),
            "base_model": args.base_model,
            "note": "pip install unsloth then wire FastLanguageModel + SFTTrainer",
        }
        (out_dir / "train_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        return 2

    # TODO: FastLanguageModel.from_pretrained + SFTTrainer when GPU account ready
    print("unsloth present — implement SFTTrainer block in train_unsloth.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
