# JARVIS Mobile (APK) — Roadmap до 1.0

> **Поточна версія:** 0.1.0 (MVP-каркас: WebView поверх сервера).
> **Ціль 1.0:** «APK = твій JARVIS» — суверенний Android-клієнт, що збирає ambient-контекст
> у **власний** сервер, дає проактив, голос, чат і computer-confirm. Privacy-first.
> **Контекст:** [`docs/CLIENTS_ROADMAP.md`](../docs/CLIENTS_ROADMAP.md) CL-3 ·
> [`docs/proposals/CL-3_mobile_context_companion.md`](../docs/proposals/CL-3_mobile_context_companion.md) ·
> [`docs/CONTEXT_MODULE.md`](../docs/CONTEXT_MODULE.md).
>
> **Легенда:** ✅ готово · 🟦 бекенд готовий, потрібна частина в APK · 🔧 TODO (APK) · 🟥 TODO + потрібен бекенд.

---

## 0. Уже зроблено (фундамент)

- ✅ **Бекенд-конвеєр контексту** (поза APK): ingest `/api/v1/ingest/events`, паспорти P9/P10,
  серверна редакція, context-jobs (summarize/daily/retention), scheduler, agent-retrieval.
- ✅ **WebView-каркас APK** (CL-3.2/3.3 seed): екран налаштування сервера + WebView + меню.
- ✅ **JWT auth бекенд** (`/api/v1/auth/login|refresh`), unified resolver.
- ✅ **Збірка APK** (`build-apk.ps1`, self-contained тулчейн) + доставка адміну (`/apk`).
- ✅ **BE1 `/context/ledger`** (журнал прозорості) + gateway-проксі + тести.

### v1.0.0 build (2026-06-16) — реалізовано в APK (компілюється; потребує device-QA)

| Реалізовано | Файли |
|-------------|-------|
| D1 onboarding + per-source toggles (default OFF) | `SettingsActivity.java` |
| D2 NotificationListenerService → черга | `NotificationCollector.java` |
| D3 SMS reader · D4 call-log reader (інкрементально) | `SmsCallSync.java` |
| D5 on-device редакція (картки/OTP/секрети) | `Redactor.java` |
| D6 локальна SQLite-черга + батч-upload | `EventQueue.java`, `UploadJobService.java`, `IngestClient.java` |
| D7 фоновий планувальник (JobScheduler, 30 хв + «sync now») | `CollectorScheduler.java` |
| E1 runtime-дозволи (SMS/calls/notif-access) | `SettingsActivity.java` |
| E3 журнал прозорості (UI → `/context/ledger`) | `SettingsActivity.java` |
| E4 one-tap purge · E5 пауза-паніка | `SettingsActivity.java` |
| B1 auth (Basic/JWT-токен) у налаштуваннях | `IngestClient.java`, `SettingsActivity.java` |

> ⚠️ Код **компілюється й входить у білд** (33 КБ APK), але **не пройшов QA на реальному пристрої**
> (NotificationListener grant, runtime-perms flow, JobScheduler-доставка). Це наступний крок.

---

## 1. Каркас і реліз

| # | Фіча | Статус |
|---|------|--------|
| A1 | WebView-shell + server URL setup | ✅ |
| A2 | Брендинг: іконка/сплеш/тема, app_name | 🔧 (зараз плейсхолдер-іконка) |
| A3 | **Signed release APK** (release keystore, не debug) | 🔧 |
| A4 | Reproducible build + фікс license-acceptance у `build-apk.ps1` | 🔧 |
| A5 | **Self-update**: перевірка `/platform/apk/info` → нотифікація → завантаження | 🟥 (треба web-ендпоінт роздачі) |

## 2. Підключення та auth

| # | Фіча | Статус |
|---|------|--------|
| B1 | Нативний логін (JWT proти `/api/v1/auth/login`) | 🟦 (бекенд ✅) |
| B2 | Пейринг сервера через QR / deep-link `jarvis://pair` | 🟥 (треба `/platform/apk/pair` + QR) |
| B3 | TLS/pubkey-pinning до власного сервера | 🔧 |
| B4 | Індикатор з'єднання / offline-стан | 🔧 |

## 3. Чат і голос

| # | Фіча | Статус |
|---|------|--------|
| C1 | Чат + streaming (SSE) | 🟦 (бекенд `/api/v1/chat` + tools.stream ✅; нативний UI/стрім TODO) |
| C2 | **Voice E2E**: запис → STT (whisper) → агент → TTS-відтворення | 🟦 (whisper/tts ✅; APK pipeline TODO) |
| C3 | Voice quick-capture зі шторки / quick-tile | 🔧 |
| C4 | Озвучений ранковий/вечірній брифінг (TTS) | 🟦 (daily-job ✅; озвучка+доставка TODO) |

## 4. Ambient-контекст (ядро 1.0 — те, заради чого APK)

| # | Фіча | Статус |
|---|------|--------|
| D1 | Onboarding дозволів + **per-source toggle (default OFF)** | 🔧 |
| D2 | **NotificationListenerService** → `/api/v1/ingest/events` | 🟦 (ingest ✅) |
| D3 | **SMS reader** (`READ_SMS`) → ingest | 🟦 |
| D4 | **Call-log reader** (`READ_CALL_LOG`, метадані) → ingest | 🟦 |
| D5 | On-device редакція (OTP/картки) перед чергою | 🟦 (серверна редакція ✅; on-device TODO) |
| D6 | Локальна шифрована черга (Room/SQLCipher) + batched upload (WorkManager) | 🔧 |
| D7 | Foreground service лісенера + battery/Wi-Fi-aware планування | 🔧 |
| D8 | Дзеркало месенджерів через нотифікації (частково) | 🔧 |

## 5. Приватність і контроль (must-have для інвазивного app)

| # | Фіча | Статус |
|---|------|--------|
| E1 | Гранулярна згода per-source + runtime-permission flow | 🔧 |
| E2 | Рівні чутливості + local-only vault (health/finance — без raw) | 🟦 (`should_store_raw` ✅; UI TODO) |
| E3 | **Журнал прозорості** (що зібрано/відправлено) | 🟥 (треба `/context/ledger` ендпоінт) |
| E4 | One-tap purge (`/api/v1/context/purge`) у UI | 🟦 (бекенд ✅) |
| E5 | Пауза-паніка (стоп усього збору одним тапом) | 🔧 |
| E6 | Per-contact include/exclude | 🔧 |
| E7 | Disclaimer згоди третіх сторін при ввімкненні calls/SMS (GDPR) | 🔧 |

## 6. Проактив (пропозиції + push)

| # | Фіча | Статус |
|---|------|--------|
| F1 | Push-транспорт (UnifiedPush/ntfy або FCM) — реєстрація | 🟥 (треба push-сервіс на бекенді) |
| F2 | Доставка daily-дайджесту (push + in-app) | 🟥 (job ✅; доставка TODO) |
| F3 | **Action proposals** у сповіщеннях (тап → виконати) | 🟥 (треба proposal-engine + behavior_profile) |
| F4 | **Computer-confirm UX** (✅/❌ з телефона) — закриває CC5 | 🟥 (треба confirm-міст на бекенді) |

---

## 7. Лінія відсічення 1.0

**У 1.0 (must):** A1–A4, B1–B4, C1–C2, D1–D7, E1–E5, E7, F1–F4.
> Тобто: встановити → спарувати/залогінитись → чат+голос → збір (сповіщення+SMS+дзвінки) з
> редакцією/opt-in/чергою → контроль приватності (ledger/purge/пауза) → daily-дайджест + проактив
> + computer-confirm через push. Підписаний реліз + self-update.

**Відкладено в 1.x (nice-to-have):**
- UsageStats-колектор (D5 розширено), edge-тріаж на пристрої, гео-пауза (E), per-contact (E6 — можна 1.0 опц.).
- Workbench-lite (mode picker, tool trace), апрув coding-агента з телефона (крос-стовп).
- Корекційний цикл summary → LoRA, групові дайджести Telegram.
- iOS (за дизайном недоступний ambient — окремий обмежений клієнт).

---

## 8. Бекенд-передумови, яких ЩЕ немає (блокують відповідні APK-фічі)

| # | Бекенд | Блокує | Статус |
|---|--------|--------|--------|
| BE1 | `/context/ledger` (read-model прозорості) | E3 | ✅ done (memory+gateway+тести) |
| BE2 | **Proposal-engine** (`build_proposals` → паспорти `kind:proposal`) | F3 | ✅ done (jarvis_core+tools+тести) |
| BE3 | **Push-сервіс** (ntfy/UnifiedPush, дефолт off) | F1, F2, F4 | ✅ done (`tools/app/push.py`, wired у daily/proposal) |
| BE4 | Web-роздача APK `/platform/apk`+`/info`+`/pair` + redeem `/api/v1/auth/pair` | A5, B2 | ✅ done (gateway+тести) |
| BE5 | Confirm-міст для mobile (`/api/v1/confirm/{pending,approve,cancel}` → tools) | F4 | ✅ done (`client_api/confirm.py`+тести) |

> Ядро + BE1–BE5 — **усі серверні прогалини закрито** (+ нативний voice `/api/v1/voice`).

### Друга хвиля APK (signed-release build, versionCode 4) — реалізовано

| Реалізовано | Файли |
|-------------|-------|
| E6 per-contact/app exclude | `Prefs.isExcluded` + колектори |
| E7 disclaimer згоди третіх сторін (SMS/calls) | `SettingsActivity` |
| F1 push-клієнт (UnifiedPush через ntfy, foreground-сервіс) | `NtfyService.java` |
| C2 нативний voice (запис → `/api/v1/voice` → STT+агент) | `Voice.java` + кнопка в Settings |
| B2 QR-пейринг (`jarvis://pair`) + A5 self-update | `Pairing.java`, `UpdateChecker.java`, `MainActivity` |
| **A3 signed-release** (release keystore, `CN=JARVIS`) + **A4 фікс license-acceptance** | `build-apk.ps1`, `app/build.gradle` |

> **Єдине, що лишилось — `device-QA`:** увесь код компілюється й у підписаному релізі, але потребує
> перевірки на фізичному Android (grant лісенера, runtime-perms, JobScheduler/ntfy-стрім, deeplink,
> запис аудіо). Це **верифікація на залізі**, не реалізація — у цьому середовищі неможлива.

---

## 9. Орієнтовний порядок (мінімізує ризик, рано дає цінність)

1. **Реліз-готовність:** A3/A4 (signed + reproducible) — щоб кожен білд був роздаваним.
2. **B1 логін + D1/D2 сповіщення + D6 черга + E1 opt-in** — перший реальний потік «телефон → сервер».
3. **E3/E4 прозорість+purge** (з BE1) — довіра до інвазивного збору.
4. **D3/D4 SMS+дзвінки + E7 disclaimer.**
5. **C2 voice E2E.**
6. **BE3 push + F2 дайджест → F3 пропозиції (BE2) → F4 computer-confirm (BE5).**
7. **A5 self-update + B2 пейринг (BE4).**

---

*Принципи — [`AGENTS.md`](../AGENTS.md) (S1 суверенність, S3 канал≠мозок, S4 human-in-the-loop, P9/P10).
Чекбокси закривати тут і в `CLIENTS_ROADMAP.md` (CL-3) у тому ж PR (D1).*
