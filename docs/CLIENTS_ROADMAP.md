# JARVIS — Clients Roadmap (Стовп C: мультиплатформа)

> **Версія:** 1.0 (2026-06-15)
> **Статус:** Living document.
> **Мета:** один бекенд — багато каналів. **Telegram** primary, **web-консоль** як штаб
> (HTML → SPA/PWA), **mobile APK** (Android) як рідний клієнт. Спільна auth і спільний API.

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Конституція — Стовп C, принципи (S3: Telegram-канал, Platform-штаб) |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Парасолька — трек C фазовий статус |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | Web-консоль `/platform` P0–P12 — база для CL-2 |
| [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) | Спільний `/v1` + auth для всіх клієнтів |
| [`docs/AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Computer-confirm UX (потрібен на mobile) |

---

## 1. Позиціонування

### 1.1 Принцип «один бекенд, багато каналів»

```
                gateway (8000)  — auth, роутинг, /platform, /v1, Mini App, bot
                       ▲
       ┌───────────────┼───────────────┬────────────────────┐
   Telegram        Web (/platform)   Mobile APK          OpenAI /v1
   (bot+MiniApp)   HTML→SPA/PWA      (Android)           (розробник)
   primary         штаб керування    рідний клієнт        Стовп A
```

Бізнес-логіка **не** дублюється на клієнтах (S3) — усі ходять у спільний client-API. Клієнт = тонкий
шар представлення + канал-специфічний UX (push, voice, deep links).

### 1.2 North Star (Стовп C)

> З телефона (APK) надиктовую голосом задачу → бачу streaming-відповідь → апрувлю computer-дію
> тапом → push-сповіщення коли фоновий job готовий. Те саме доступно в браузері (PWA, офлайн-shell)
> і в Telegram. Перемкнувся на ноут — та сама сесія, пам'ять, проєкти.

### 1.3 Принципи (Стовп C)

- **Telegram лишається primary** — не замінюємо, доводимо інші канали до parity (S3).
- **Спільний контракт:** усі клієнти — через `/api/v1/*` + `/v1`, єдина auth (JWT + Telegram initData).
- **Self-hosted працює без HTTPS-домену** — Telegram через polling; web локально; mobile через LAN/tunnel.
- **Progressive enhancement:** web HTML працює без JS-фреймворка; SPA/PWA — наступний шар, не перепис із нуля.

---

## 2. Baseline (стан на 2026-06-15)

### 2.1 Реалізовано

| Канал | Стан | Файли |
|-------|------|-------|
| Telegram bot | ✅ polling, auth, роутинг text/voice/file | `gateway/app/router.py`, `gateway/app/bot/` |
| Telegram Mini App | ✅ `/app` дашборд, initData HMAC | `gateway/app/webapp.py`, `static/app.html` |
| Web-консоль `/platform` | ✅ 19 табів, білінгва, P0–P12 | `gateway/app/platform/*`, `static/platform.html` |
| Admin-панель (legacy) | ✅ `/admin` | `gateway/app/admin_panel.py`, `static/admin.html` |
| OpenAI `/v1` | ✅ opt-in | `gateway/app/openai_api.py` |
| Mobile APK | ❌ немає | — |
| Спільна auth (JWT) | ❌ лише initData/Basic/global-key | `gateway/app/platform/auth.py` |

### 2.2 Оцінка зрілості (чесно)

| Канал | Оцінка | Коментар |
|-------|--------|----------|
| Telegram | **8/10** | зрілий: bot+MiniApp, voice, computer-confirm, deep links |
| Web `/platform` | **6/10** | багатий функціонал, але server-rendered HTML (~1460 рядків), не SPA/PWA, без offline/push |
| Mobile | **0/10** | відсутній |
| Спільна auth | **3/10** | три різні шляхи (initData/Basic/global-key); немає JWT для mobile/SPA |
| Крос-клієнт sync | **5/10** | пам'ять/проєкти спільні в БД, але немає явної session-continuity UX |

### 2.3 Розриви (gap list)

| # | Gap | Вплив |
|---|-----|-------|
| CC1 | Немає JWT-auth → mobile/SPA не мають чистого логіну | Блокер для CL-3 |
| CC2 | `platform.html` — моноліт HTML, не SPA/PWA | Немає offline, push, code-split |
| CC3 | Немає mobile-клієнта | Стовп C неповний |
| CC4 | Client-API розкиданий (`/app/*`, `/platform/api/*`, `/v1`) | Немає єдиного контракту для клієнтів |
| CC5 | Computer-confirm лише в Telegram/Workbench | На mobile/SPA нема нативного апруву |
| CC6 | Push-сповіщення лише через Telegram | Mobile/web не отримують async-нотифікації |

---

## 3. Фази розвитку (CL-0…CL-5)

```
CL-0 (TG+MiniApp+/platform ✅) ─► CL-1 (спільний client-API + JWT)
   ─► CL-2 (web SPA/PWA) ─► CL-3 (mobile APK) ─► CL-4 (TG parity) ─► CL-5 (desktop/sync)
```

---

## CL-0 — Baseline · ✅ **done**

| # | Задача | Статус |
|---|--------|--------|
| CL-0.1 | Telegram bot (polling, auth, text/voice/file) | [x] |
| CL-0.2 | Telegram Mini App `/app` (initData HMAC) | [x] |
| CL-0.3 | Web-консоль `/platform` P0–P12 (білінгва) | [x] |

---

## CL-1 — Спільний client-API + єдина auth · **блокується SAAS PR#1**

**Мета:** один контракт для всіх клієнтів; JWT поряд із initData.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CL-1.1 | JWT auth (signup/login/refresh) — `gateway/app/saas/auth.py` | SAAS PR#6 | [ ] |
| CL-1.2 | `link-telegram` — JWT-акаунт ↔ telegram_id (зберегти legacy дані) | SAAS §6.1 | [ ] |
| CL-1.3 | Консолідувати client-API: `/app/*` + `/platform/api/*` → стабільний `/api/v1/*` | Versioned контракт | [ ] |
| CL-1.4 | Auth-матриця: Telegram initData · JWT · API-key · Basic — один resolver | `RequestContext` (SAAS §2.2) | [ ] |
| CL-1.5 | OpenAPI для client-API (для генерації mobile-клієнта) | `/openapi.json` | [ ] |

**Вихід CL-1:** будь-який клієнт логіниться (JWT або initData) і ходить в єдиний `/api/v1/*`.

---

## CL-2 — Web-app v2 (SPA/PWA) · **4–6 тижнів**

**Мета:** `/platform` HTML → справжній web-app з offline-shell і push.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CL-2.1 | ADR: фреймворк (vanilla+Vite / React / Svelte) — баланс ваги й DX | `docs/adr/` | [ ] |
| CL-2.2 | Поетапна міграція табів (overview→workbench→…) без big-bang | Кожен таб окремо | [ ] |
| CL-2.3 | PWA: service worker, manifest, offline-shell, install-prompt | Lighthouse PWA pass | [ ] |
| CL-2.4 | Web Push (VAPID) для async job-нотифікацій | Дозвіл + доставка | [ ] |
| CL-2.5 | Зберегти білінгву (uk/en) і a11y (role=tab) з поточного | Parity з HTML-версією | [ ] |
| CL-2.6 | Login overlay (JWT) коли немає Telegram initData | SAAS §8.3 | [ ] |

> **Не big-bang:** поточний `platform.html` лишається робочим, поки таби мігрують по одному (P6 принцип
> «vanilla JS до P6+, Vite опційно пізніше» — тепер настав час Vite).

**Вихід CL-2:** `/platform` встановлюється як PWA, працює офлайн-shell, шле push.

---

## CL-3 — Mobile APK (Android) · **6–10 тижнів**

**Мета:** рідний Android-клієнт поверх `/api/v1/*` + `/v1`.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CL-3.1 | ADR: стек (PWA-wrap / Flutter / React Native / Kotlin) — критерій: швидкість + voice/push | `docs/adr/` | [ ] |
| CL-3.2 | Каркас `mobile/`: логін (JWT), список чатів, налаштування сервера (URL) | APK збирається | [ ] |
| CL-3.3 | Чат + streaming (SSE/WebSocket) | Друкована відповідь | [ ] |
| CL-3.4 | Voice: запис → STT (whisper) → агент → TTS-відтворення | E2E voice | [ ] |
| CL-3.5 | Computer-confirm UX (тап ✅/❌, перегляд дії) — закриває CC5 | Inline approve | [ ] |
| CL-3.6 | Push (FCM) для job/reminder/confirm-pending | Доставка у фоні | [ ] |
| CL-3.7 | Workbench-lite (mode picker, tool trace) | Mobile-friendly | [ ] |
| CL-3.8 | Реліз: signed APK + (опц.) F-Droid/Play | `mobile/README` build | [ ] |

> **Рекомендація для оцінки:** почати з **PWA-wrap** (CL-2 PWA у WebView + нативні voice/push мости) —
> найдешевший шлях до APK, що перевикористовує web-app. Рідний (Flutter/RN) — якщо PWA впреться в
> ліміти voice/computer-confirm UX. Рішення фіксуємо в ADR (CL-3.1).

**Вихід CL-3:** встановлюваний APK: чат, voice, computer-confirm, push — проти власного сервера.

---

## CL-4 — Telegram parity · **паралельно, 🟡 частково**

**Мета:** Telegram не відстає від web/mobile по фічах.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CL-4.1 | Deep links для всіх ключових екранів (`/start app\|mode_*\|canvas`) | Існує частково | 🟡 |
| CL-4.2 | Mini App parity з Platform-табами (єдиний API CL-1.3) | Спільні дані | [ ] |
| CL-4.3 | Named tunnel лише для `/app` (opt-in), бот лишається на polling | ROADMAP N2/F | [ ] |
| CL-4.4 | Coding-агент (Стовп B) і `/v1`-playground доступні з Telegram | Команди | [ ] |

**Вихід CL-4:** усе, що в web/mobile, доступне і з Telegram (де доречно для месенджера).

---

## CL-5 — Desktop / крос-клієнт sync · **опційно, 8–12 тижнів**

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CL-5.1 | Desktop tray (host-agent indicator: idle/working/confirm) | AGENT_MODE AM-3.5 | [ ] |
| CL-5.2 | Electron/Tauri-обгортка web-app (опц.) | Один бінар | [ ] |
| CL-5.3 | Session-continuity UX: «продовжити на іншому пристрої» | Спільна сесія в БД | [ ] |
| CL-5.4 | Крос-клієнт presence/notification dedup | Не дублювати push | [ ] |

**Вихід CL-5:** перемикання між пристроями без втрати контексту.

---

## 4. Канал-матриця (ціль)

| Фіча | Telegram | Web (PWA) | Mobile APK | `/v1` API |
|------|----------|-----------|------------|-----------|
| Чат + streaming | ✅ | ✅ | CL-3 | ✅ |
| Voice (STT/TTS) | ✅ | CL-2 | CL-3 | — |
| Workbench / agent modes | ⚪ lite | ✅ | CL-3 lite | ✅ |
| Computer-confirm | ✅ | ✅ | CL-3.5 | — |
| Projects / Memory | ⚪ | ✅ | CL-3 | через API |
| Push-нотифікації | ✅ | CL-2.4 | CL-3.6 | webhook |
| Coding-агент (Стовп B) | CL-4.4 | CA-6.5 tab | CL-3 | CLI/IDE |
| Developer console (Стовп A) | — | AP-3 | — | — |

---

## 5. KPI

| KPI | Ціль | Як міряти |
|-----|------|-----------|
| Крос-клієнт feature parity | > 90% | канал-матриця |
| Web Lighthouse PWA | pass (installable, offline) | CI Lighthouse |
| Mobile: cold start → чат | < 3 с | ручне QA |
| Спільна auth (один логін усюди) | 1 акаунт | інтеграційний тест |
| Push доставка (job done) | > 95% | метрика доставки |

---

## 6. Свідомо не робимо

- **Замінити Telegram єдиним каналом** — TG лишається primary (S3).
- **Big-bang перепис `platform.html`** — поетапна міграція табів (CL-2.2).
- **Дублювати бізнес-логіку на клієнтах** — усе через `/api/v1/*` (S3).
- **Вимагати HTTPS-домен для self-hosted** — TG polling, web локально, mobile через LAN/tunnel.
- **iOS до Android** — фокус APK спершу (ресурс/розповсюдження); iOS — за попитом.

---

## 7. Залежності

| Залежність | Звідки |
|------------|--------|
| JWT auth, RequestContext, link-telegram | [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) PR#1/#6 |
| Web-консоль база (таби, i18n) | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) P0–P12 |
| `/v1` + client-API контракт | [`API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) AP-1/AP-2 |
| Computer-confirm логіка | [`AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) |
| STT/TTS сервіси | `whisper/`, `tts/` |

---

## 8. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-15 | 1.0 | Початковий roadmap Стовпа C (CL-0…CL-5): web SPA/PWA, mobile APK, TG parity |

---

*Оновлюйте чекбокси при закритті задач. Принципи: [`AGENTS.md`](../AGENTS.md) · Парасолька: [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md)*
