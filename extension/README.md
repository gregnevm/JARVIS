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
`navigate{url}` · `read` (текст сторінки) · `click{selector}` · `fill{selector,value}` · `eval{script}`.

## Безпека
- Auth — той самий JWT, що й клієнти (`Authorization: Bearer`).
- Команди org-scoped у Redis (TTL 120с); нічого не виконується без валідного токена.
- `eval` — потужний; вмикай лише для довіреного власного сервера.
