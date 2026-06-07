# JARVIS Training (PortableAI Twin)

## Експорт даних

```powershell
# Після кількох діалогів (session_ingest → data/logs/sessions/)
.\scripts\export_dataset.ps1

# Або API
curl -X POST "http://127.0.0.1:8200/dataset/export/sharegpt"
curl "http://127.0.0.1:8200/dataset/stats"
```

Вихід: `data/twin/export/sharegpt.jsonl` + `sharegpt_holdout.jsonl`.

## Eval (format gate)

```bash
python training/eval/run_eval.py --dataset data/twin/export/sharegpt_holdout.jsonl
```

## LoRA (майбутнє D.1)

- RunPod + Unsloth: `training/runpod/train_lora.sh` + `train_unsloth.py`
- Валідація даних без GPU: `python training/runpod/train_unsloth.py --dry-run --data-dir ...`
- Після train: `POST twin:8765/registry/lora` → promote у Mini App / Platform

## Twin registry

- Promote / rollback: Telegram Mini App → Twin Sync (адмін)
- HTTP: `POST /registry/lora/{version}/promote`, `POST /registry/lora/rollback`
