# JARVIS — backup і відновлення

> Операційний runbook для Фази 0 ([`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) §0.1.4).

## Що бекапити

| Артефакт | Шлях | Навіщо |
|----------|------|--------|
| Дані користувача | `data/` (uploads, access, logs, twin, macros, `logs/sessions/`) | Нотатки, whitelist, аудит, registry, session JSONL |
| PostgreSQL | Docker volume `jarvis_postgres_data` (ім’я з `docker volume ls`) | Сесії, повідомлення, embeddings |
| Конфіг | `.env` (окремо, **не в публічний git**) | Токени, whitelist |
| Host-agent | `hostagent/.env` якщо є | Токен, FS roots |

Рекомендована частота: **щодня** `data/` + registry; **щотижня** повний snapshot postgres.

## Швидкий бекап (PowerShell)

```powershell
cd O:\JARVIS
$stamp = Get-Date -Format "yyyy-MM-dd"
$dest = "D:\Backups\jarvis\$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# data + twin
Copy-Item -Recurse -Force .\data $dest\data

# .env (зашифруйте архів паролем у проді)
Copy-Item -Force .\.env $dest\.env

# postgres dump (потрібен running postgres)
docker compose exec -T postgres pg_dump -U jarvis jarvis > "$dest\jarvis.sql"
```

## rclone (опційно, DESIGN §10.4)

```powershell
# один раз: rclone config → remote "b2" або NAS
rclone sync O:\JARVIS\data remote:jarvis-backup/data --transfers 4
rclone copy O:\JARVIS\data\twin\registry.db remote:jarvis-backup/twin/
```

Retention: 30 днів для `data/`, 10 версій для LoRA (коли з’явиться training).

## Відновлення

1. Зупинити стек: `docker compose down`
2. Відновити `data/` з бекапу в корінь репо
3. Postgres:
   ```powershell
   docker compose up -d postgres
   # зачекати healthy
   Get-Content D:\Backups\jarvis\YYYY-MM-DD\jarvis.sql | docker compose exec -T postgres psql -U jarvis jarvis
   ```
4. Перевірити `.env` (токени, `ALLOWED_USER_IDS`)
5. Підняти все: `.\scripts\autostart.ps1` або `docker compose up -d --build`
6. Перевірка: `.\scripts\verify_stack.ps1` + [`SMOKE_TEST.md`](SMOKE_TEST.md)

## Rollback LoRA (коли є Twin training)

1. `twin` ModelRegistry: `rollback` на попередню версію (див. `docs/DESIGN.md` §10.4)
2. Синхронізувати Ollama Modelfile / adapter
3. Smoke у Telegram (5–10 пунктів)

## Не бекапити в git

- `.env`, `hostagent/.env`
- `data/logs/*.jsonl` з PII — лише зашифровані архіви
- `vendor/sd-forge/venv` — відновлюється скриптами setup
