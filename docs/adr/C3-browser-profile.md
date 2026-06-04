# ADR: C3 Browser — профіль Chrome / Playwright

**Статус:** прийнято (Фаза 2)  
**Контекст:** агенту потрібен headless браузер у `tools` для `browser_*` (T2).

## Рішення

| Режим | Опис | Коли |
|-------|------|------|
| **A — чистий headless** (дефолт) | `chromium.launch(headless=True)` без `user_data_dir`, нова сесія на процес tools | Прод, публічні URL, smoke |
| **B — persistent profile** (майбутнє) | `user_data_dir` на volume `data/browser-profile/` | Логін у SaaS, cookies між рестартами |

**Зараз реалізовано A.** B потребує окремого volume, політики секретів (cookies = credentials) і confirm на `browser_open` до довірених доменів.

## Наслідки

- Логіни Google/GitHub у headless без profile **не зберігаються** між рестартами контейнера.
- Для «залогіненого» сценарію: увімкнути B + whitelist доменів у roadmap C5.
- CDP до локального Chrome користувача **не** використовується (ізоляція від робочого браузера).

## Альтернативи (відхилено)

- **Selenium + системний Chrome** — важче в Docker, дублює Playwright.
- **CDP на desktop Chrome** — ризик витоку сесії користувача на хості.

## Посилання

- [`tools/app/browser.py`](../../tools/app/browser.py)
- [`docs/COMPUTER_USE.md`](../COMPUTER_USE.md) § C3
