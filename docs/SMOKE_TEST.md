# JARVIS — smoke-тест у Telegram

Автоматично перевірено (2026-06-04): health усіх сервісів, pytest по сервісах,
gateway `ingest=polling`, tools → hostagent з Docker.

Познач у чаті ✅/❌ після ручної перевірки.

| # | Фіча | Дія в Telegram | Очікування |
|---|------|----------------|------------|
| 1 | Текст | Звичайне повідомлення | Відповідь за кілька секунд |
| 2 | Streaming | Довгий запит (пошук/агент) | «✍️ думаю…» → текст оновлюється |
| 3 | Голос → текст | Voice note | Транскрипт + відповідь |
| 4 | Голос ← TTS | Voice note | Голосова відповідь (або текст-фолбек) |
| 5 | Фото | Надіслати image | Опис / відповідь |
| 6 | Файл | PDF або документ | Парсинг + відповідь |
| 7 | Альбом | 2+ фото в одному альбомі | Одна обробка після паузи |
| 8 | Реакція | Emoji на повідомлення бота | Коротка репліка |
| 9 | Нотатка | «запам'ятай …» | Підтвердження запису |
| 10 | Нагадування | «нагадай через 2 хв …» | Повідомлення ⏰ через ~2 хв |
| 11 | Команди | `/status`, `/dashboard`, `/mode` | Статус без помилок |
| 12 | Mini App | http://localhost:8000/app | Дашборд відкривається |
| 13 | Computer | `/mode computer`, read-only PS | Відповідь з host-agent |
| 14 | Підтвердження | Mutating PS/fs (якщо тестуєш) | Inline ✅/❌ |
| 15 | code_exec | «порахуй factorial 10 у python» | Результат (ENABLE_CODE_EXEC=true) |
| 16 | /app | `/app` (не fs_list) | Інструкція або кнопка Mini App |
| 17 | Скріншот | «зроби скріншот» (computer/hybrid) | Фото екрана в чаті |
| 18 | Computer confirm | Mutating + ✅ | Результат + follow-up від агента |
| 19 | Deep link | `/start mode_agent` | Режим змінено |
| 20 | cancel reminder | «скасуй нагадування …» після /reminders | Скасовано |
| 21 | `/macro list` | Список макросів (deploy, stack-status, …) | HTML-список |
| 22 | `/macro run stack-status` | Read-only CLI macro | Вивід `docker compose ps` |
| 23 | Health watch | Зупинити Ollama ~5 хв → старт | 🔴 alert → ✅ online (якщо `HEALTH_WATCH_INTERVAL>0`) |
| 24 | Browser C3 | `ENABLE_BROWSER=true`, `/mode computer`, «відкрий https://example.com» | Текст сторінки; click/fill → ✅/❌ |
| 25 | `/reminders ics` | Після `set_reminder` | Файл `.ics` у Telegram |
| 26 | UIA C4 | `/mode computer`, «список вікон» | `window_list` / focus |

**Автоматична перевірка хоста:** `.\scripts\verify_stack.ps1` (compose, HTTP, Ollama, host-agent).

Якщо щось падає: `docker compose logs -f gateway tools` та `data/autostart.log` (autostart).
Після ребуту: autostart → verify → пункти 1–5 у Telegram.
