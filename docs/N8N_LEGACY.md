# n8n — legacy (не default)

**Статус (Фаза 3 A.4):** агент-луп живе в **Tools** (`/agent`, `/agent/stream`). n8n не потрібен для Telegram E2E.

## Поточний default

```
Telegram → gateway (polling) → tools/agent → Ollama / toolkit
```

## Коли n8n ще має сенс

- Старі workflow у `n8n/workflows/` для одноразових інтеграцій (email, CRM).
- Експерименти без зміни коду gateway.

## Міграція

1. Вимкни webhook n8n на той самий Telegram-токен (конфлікт getUpdates).
2. `TELEGRAM_INGEST_MODE=polling` у `.env`.
3. Перенеси логіку в `tools/app/toolkit.py` або gateway bot commands.
4. Docker: сервіс `n8n` можна не піднімати в `docker compose up`.

## Посилання

- [`README.md`](../README.md) — архітектура без n8n-проксі
- [`DESIGN.md`](DESIGN.md) § pipeline
