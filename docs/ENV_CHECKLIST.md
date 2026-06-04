# JARVIS — чеклист змінних середовища (ops)

Після merge residual-фіксів перевір `.env` на хості (не комітити секрети).

## Обовʼязково для Computer Use + FS

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `ENABLE_COMPUTER_USE` | `true` | Агент + host tools (скріншот, PS, FS) |
| `HOSTAGENT_TOKEN` | *(секрет)* | Звʼязок tools ↔ hostagent |
| `HOSTAGENT_FS_ROOTS` | `C:\Users\you\Documents,O:\JARVIS` | Обмеження шляхів FS (comma-separated). Без цього — доступ до будь-якого абсолютного шляху на хості |

Hostagent читає `HOSTAGENT_FS_ROOTS` як `fs_roots` у `hostagent/.env` або через compose.

## Telegram Mini App / deep link

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `PUBLIC_APP_URL` | `https://your-tunnel.example/app` | HTTPS URL для Web App кнопки (`/app`, `/start canvas`). Без HTTPS — текстовий фолбек |

Deep link `/start canvas` додає `?canvas=1` до URL Mini App.

## Нагадування

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `REMINDER_POLL_SECONDS` | `5` | Інтервал полера gateway для due reminders |

## Безпека (рекомендовано)

| Змінна | Навіщо |
|--------|--------|
| `TELEGRAM_WEBHOOK_SECRET` | Перевірка `X-Telegram-Bot-Api-Secret-Token` у webhook-режимі |
| `COMPUTER_MODE_ADMINS_ONLY` | Обмежити `/mode computer` |
| **M4** | Ротація `TELEGRAM_BOT_TOKEN` у @BotFather після витоку в логах/чаті |

## Після змін

```powershell
cd O:\JARVIS\hostagent; .\run.bat
cd O:\JARVIS
docker compose up -d --build gateway tools
```

Тести: `pytest gateway/tests tools/tests hostagent/tests`
