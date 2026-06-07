#!/usr/bin/env bash
# JARVIS PortableAI — one-click Edge (Linux)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

KOBOLD="./engines/linux/koboldcpp"
MODEL="./models/qwen2.5-7b-instruct-q4_k_m.gguf"

if [[ ! -x "$KOBOLD" ]]; then
  echo "Place koboldcpp binary in engines/linux/"
  exit 1
fi
if [[ ! -f "$MODEL" ]]; then
  echo "Place GGUF model at $MODEL"
  exit 1
fi

LORA_ARGS=()
if [[ -f lora/active/jarvis.gguf ]]; then
  LORA_ARGS=(--lora lora/active/jarvis.gguf)
fi

"$KOBOLD" \
  --model "$MODEL" \
  "${LORA_ARGS[@]}" \
  --contextsize 4096 \
  --threads 8 \
  --port 5001 \
  --launch &

[[ -f config.yaml ]] || cp config.yaml.example config.yaml
python3 edge_sync.py --loop &

wait
