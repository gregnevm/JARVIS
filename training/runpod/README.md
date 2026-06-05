# RunPod + Unsloth (D.1 placeholder)

1. Upload `data/twin/export/sharegpt.jsonl` to volume.
2. Run Unsloth QLoRA on base `qwen2.5:7b-instruct` (ADR-007).
3. Register artifact: `POST http://twin:8765/registry/lora` with `version`, `path`, `eval_score`.
4. Promote via Mini App or `POST /registry/lora/{version}/promote`.

Scripts:
- `train_lora.sh` — викликає `train_unsloth.py`
- `train_unsloth.py` — skeleton (exit 2 без unsloth; exit 0 коли SFTTrainer додано)

Після export: `data/twin/export/sharegpt.jsonl` → скопіювати як `train.jsonl` на volume.
