# Computer Use — відкат шкоди (C5.3)

Якщо агент або макрос зробив небажану зміну на Windows-хості.

## 1. Негайно

1. **Скасувати pending** — у Telegram `❌` на confirm або `/tasks` cancel (якщо є фонова задача).
2. **Вимкнути Computer Use** — `.env`: `ENABLE_COMPUTER_USE=false` → `docker compose up -d tools gateway`.
3. **Revoke trust** — Mini App Remote → або `DELETE /computer/trust` (адмін).

## 2. Файли та FS

- Перевір `data/logs/computer.jsonl` — останні `tool`, `args`, `result_preview`.
- Якщо було `fs_write` / `fs_write_bytes` — віднови з бекапу [`BACKUP.md`](BACKUP.md) або VSS (Windows «Попередні версії»).
- `HOSTAGENT_FS_ROOTS` обмежує майбутні шляхи; не розширюй roots без потреби.

## 3. Whitelist / learned

```powershell
# Перегляд
Get-Content O:\JARVIS\data\computer_learned.json

# Скинути навчені cmdlet/exe (залишиться .env PS_WHITELIST / CLI_WHITELIST)
Remove-Item O:\JARVIS\data\computer_learned.json -ErrorAction SilentlyContinue
docker compose restart tools
```

## 4. Admin PowerShell

- Тимчасово: `COMPUTER_ALLOW_ADMIN=false` + `HOSTAGENT_ALLOW_ADMIN=0` → restart hostagent.
- Перевір UAC-журнал Windows, якщо elevation спрацювало.

## 5. Docker / сервіси

Якщо чіпали `docker compose` / сервіси:

```powershell
cd O:\JARVIS
docker compose ps
docker compose up -d   # повернути очікуваний стан
.\scripts\verify_stack.ps1
```

## 6. Після інциденту

- Знизь `COMPUTER_RATE_LIMIT_PER_HOUR` (напр. 30).
- Ротація `HOSTAGENT_TOKEN` якщо підозра на витік.
- M4: ротація `TELEGRAM_BOT_TOKEN` при витоку в чат/логи.

## Посилання

- [`COMPUTER_USE.md`](COMPUTER_USE.md)
- [`ENV_CHECKLIST.md`](ENV_CHECKLIST.md)
