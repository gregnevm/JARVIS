#!/usr/bin/env python3
"""D.1 — Unsloth QLoRA (RunPod). ShareGPT JSONL → LoRA adapter + optional GGUF."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROLE_MAP = {"human": "user", "gpt": "assistant", "system": "system"}


def load_sharegpt_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON line {i} in {path}: {exc}") from exc
    return rows


def validate_sharegpt(records: list[dict[str, Any]]) -> tuple[int, list[str]]:
    valid = 0
    issues: list[str] = []
    for i, rec in enumerate(records):
        conv = rec.get("conversations")
        if not isinstance(conv, list) or len(conv) < 2:
            issues.append(f"row {i}: need conversations[>=2]")
            continue
        ok = True
        for j, turn in enumerate(conv):
            if not isinstance(turn, dict):
                issues.append(f"row {i} turn {j}: not an object")
                ok = False
                break
            if "from" not in turn or "value" not in turn:
                issues.append(f"row {i} turn {j}: missing from/value")
                ok = False
                break
        if ok:
            valid += 1
    return valid, issues


def sharegpt_to_messages(conversations: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for turn in conversations:
        role = _ROLE_MAP.get(str(turn.get("from", "")), "user")
        content = str(turn.get("value", ""))
        if content:
            out.append({"role": role, "content": content})
    return out


def conversations_to_text(tokenizer: Any, conversations: list[dict[str, Any]]) -> str:
    messages = sharegpt_to_messages(conversations)
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    parts: list[str] = []
    for msg in messages:
        parts.append(f"{msg['role']}: {msg['content']}")
    return "\n".join(parts)


def dry_run(args: argparse.Namespace, records: list[dict[str, Any]], out_dir: Path) -> int:
    valid, issues = validate_sharegpt(records)
    meta = {
        "status": "dry_run",
        "samples_total": len(records),
        "samples_valid": valid,
        "base_model": args.base_model,
        "max_steps": args.max_steps,
        "issues": issues[:20],
    }
    (out_dir / "train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    if valid == 0:
        print("No valid ShareGPT rows.", file=sys.stderr)
        return 1
    return 0


def run_training(args: argparse.Namespace, records: list[dict[str, Any]], out_dir: Path) -> int:
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel

    valid, issues = validate_sharegpt(records)
    if valid == 0:
        print("No valid ShareGPT rows.", file=sys.stderr)
        return 1
    if issues:
        print(f"Skipping {len(issues)} invalid rows (see train_meta.json)", file=sys.stderr)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    texts: list[str] = []
    for rec in records:
        conv = rec.get("conversations")
        if not isinstance(conv, list) or len(conv) < 2:
            continue
        texts.append(conversations_to_text(tokenizer, conv))

    dataset = Dataset.from_dict({"text": texts})
    adapter_dir = out_dir / "lora_adapter"
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        args=SFTConfig(
            output_dir=str(adapter_dir),
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=max(1, args.max_steps // 20),
            max_steps=args.max_steps,
            learning_rate=args.learning_rate,
            logging_steps=min(10, max(1, args.max_steps // 10)),
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            report_to="none",
        ),
    )
    trainer.train()

    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    gguf_name = args.gguf_name
    if args.export_gguf:
        print(f"Export GGUF {gguf_name} ({args.gguf_quant}) …")
        model.save_pretrained_gguf(gguf_name, tokenizer, quantization_method=args.gguf_quant)

    meta = {
        "status": "trained",
        "samples_total": len(records),
        "samples_trained": len(texts),
        "base_model": args.base_model,
        "max_steps": args.max_steps,
        "adapter_dir": str(adapter_dir),
        "gguf": gguf_name if args.export_gguf else None,
    }
    (out_dir / "train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="JARVIS LoRA train (Unsloth QLoRA)")
    p.add_argument("--data-dir", default="/workspace/data")
    p.add_argument("--output-dir", default="/workspace/output/lora")
    p.add_argument("--base-model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit")
    p.add_argument("--train-file", default="train.jsonl")
    p.add_argument("--max-steps", type=int, default=200)
    p.add_argument("--max-seq-length", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=2e-4)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=16)
    p.add_argument("--gguf-name", default="lora_v1")
    p.add_argument("--gguf-quant", default="q4_k_m")
    p.add_argument("--export-gguf", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    train_path = data_dir / args.train_file
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not train_path.is_file():
        print(f"Missing train file: {train_path}", file=sys.stderr)
        return 1

    records = load_sharegpt_jsonl(train_path)
    print(f"Train samples: {len(records)} base={args.base_model} steps={args.max_steps}")

    if args.dry_run:
        return dry_run(args, records, out_dir)

    try:
        import unsloth  # noqa: F401
    except ImportError:
        print(
            "unsloth not installed. On RunPod:\n"
            "  pip install unsloth\n"
            "  python train_unsloth.py --dry-run  # validate data only",
            file=sys.stderr,
        )
        meta = {
            "status": "missing_unsloth",
            "samples": len(records),
            "base_model": args.base_model,
            "note": "pip install unsloth datasets trl on GPU pod",
        }
        (out_dir / "train_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        return 2

    return run_training(args, records, out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
