#!/usr/bin/env bash
# D.1 — RunPod / Unsloth LoRA (skeleton). Upload sharegpt.jsonl to $DATA_DIR first.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/workspace/data}"
BASE_MODEL="${BASE_MODEL:-unsloth/Qwen2.5-7B-Instruct-bnb-4bit}"
OUTPUT_DIR="${OUTPUT_DIR:-/workspace/output/lora}"

echo "Train LoRA: base=$BASE_MODEL data=$DATA_DIR/train.jsonl"
ls -la "$DATA_DIR" || true
mkdir -p "$OUTPUT_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/train_unsloth.py" \
  --data-dir "$DATA_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --base-model "$BASE_MODEL" \
  --train-file train.jsonl
rc=$?
echo "train_unsloth.py exit=$rc"
exit "$rc"
