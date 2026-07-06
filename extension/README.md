# JARVIS Chrome Bridge (extension endpoint)

Двосторонній міст «JARVIS ↔ браузер»: сервер кладе команди в чергу
(`POST /api/v1/chrome/command`), розширення опитує (`/poll`), виконує в активній
вкладці й повертає результат (`/result`). Доповнює headless-Playwright контролем
**реального** браузера користувача.

## Встановлення (sideload, як і APK)
1. `chrome://extensions` → увімкни **Developer mode**.
2. **Load unpacked** → вкажи теку `extension/`.
3. Клік на іконку → впиши **Сервер** (URL твого JARVIS) і **JWT-токен**
   (отримай у застосунку через Telegram-логін або пейринг) → Зберегти.

## Підтримувані команди
`navigate{url}` · `location` (URL активної вкладки) · `read` (текст сторінки) ·
`schema` (жива схема форми input/select/textarea → JSON-рядок) ·
`click{selector}` · `fill{selector,value}` (React-стійке присвоєння) · `eval{script}`.

> `location`/`schema`/`fill` — **CSP-safe** (без `eval`), тож працюють навіть на сторінках, що
> блокують `eval`. Саме їх використовує `erp_sa`-адаптер (autofill) — power-`eval` йому не потрібен.

## Безпека
- Auth — той самий JWT, що й клієнти (`Authorization: Bearer`). Отримати: `POST /api/v1/auth/login`
  (`{username:"admin", password:<ADMIN_PANEL_PASSWORD|PLATFORM_PASSWORD>}`) → `access_token` (TTL 1год).
- Команди org-scoped у Redis (TTL 120с); нічого не виконується без валідного токена. Черга keyed by
  `(org_id, uid)` — токен має резолвитись у того самого користувача, що й клієнт-адаптер (інакше різні черги).
- `eval` — потужний; вмикай лише для довіреного власного сервера.
