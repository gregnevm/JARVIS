# ADR: CL-3 Mobile — стек MVP-клієнта (Android APK)

**Статус:** прийнято (Стовп C, Фаза CL-3, MVP v0.1.0)
**Контекст:** потрібен **рідний Android-клієнт** проти власного JARVIS-сервера
(чат, потім voice/push/computer-confirm). [`CLIENTS_ROADMAP.md`](../CLIENTS_ROADMAP.md)
CL-3.1 вимагає зафіксувати стек; критерій — **швидкість до робочого APK** + перевикористання
наявної веб-консолі, без дублювання бізнес-логіки на клієнті (AGENTS.md S3).

## Рішення

**MVP = нативний WebView-каркас (Java, без AndroidX, без сторонніх залежностей)**, що
відкриває веб-консоль/Mini App сервера. Адреса сервера налаштовується при першому
запуску (LAN або tunnel) і зберігається в `SharedPreferences`.

| Аспект | Вибір | Чому |
|--------|-------|------|
| Тип | Нативний WebView-wrapper (1 `Activity`) | Найдешевший шлях до APK; перевикористовує `/app` та `/platform` |
| Мова | Java (framework `android.webkit`) | Без Kotlin-stdlib/AndroidX → легкий, офлайн-дружній білд |
| Залежності | **нуль** (лише Android framework) | Білд не потребує Maven-резолву; YAGNI (P6) |
| Білд | Gradle 8.7 + AGP 8.5 (compileSdk 34, minSdk 24) | Стандарт; self-contained тулчейн у `build-apk.ps1` |
| Підпис | debug-keystore (авто) | Достатньо для особистого install; release-keystore → CL-3.8 |
| Конфіг сервера | `SharedPreferences`, екран при 1-му запуску | Self-hosted без фіксованого домену (S2): LAN/tunnel |
| Cleartext | `usesCleartextTraffic` + network-security-config | Self-hosted часто http на LAN без HTTPS-домену |

**Чому не TWA (Trusted Web Activity / Bubblewrap):** TWA розрахований на **фіксований
опублікований PWA-домен** із Digital Asset Links. Self-hosted JARVIS — це змінний
LAN-IP/tunnel без сталого домену, тож TWA ховання URL-бару не спрацює, а налаштовуваний
WebView гнучкіший. PWA-shell (CL-2) лишається паралельним треком для браузера.

## Наслідки

- APK збирається з `mobile/build-apk.ps1` (качає JDK17 + Android SDK + Gradle локально у
  `mobile/.toolchain/`), кладе у `data/artifacts/jarvis-mvp.apk` + паспорт `*.meta.json`.
- Бот віддає файл командою **`/apk`** ([`gateway/app/bot/apk.py`](../../gateway/app/bot/apk.py) +
  [`gateway/app/apk_artifact.py`](../../gateway/app/apk_artifact.py)); адмін отримує його авто
  після білду ([`scripts/send_apk_to_admin.py`](../../scripts/send_apk_to_admin.py)).
- Voice/STT (CL-3.4): мікрофон уже прокинуто у WebView (`onPermissionRequest`), але повний
  E2E-voice — наступна ітерація.
- Поки немає JWT-логіну (CC1) — клієнт показує `/app` (initData-dev-open) або `/platform`
  (Basic). Нативний JWT-логін приходить із CL-1.1/SAAS PR#6 і замінює WebView-екрани поступово.

## Альтернативи (відхилено для MVP)

- **Flutter / React Native** — багатший UX, але важчий тулчейн і довший шлях до першого APK;
  розглядаємо, якщо WebView впреться в ліміти voice/computer-confirm (як зафіксовано в CL-3.1).
- **TWA / Bubblewrap** — прив'язка до сталого домену + Asset Links (див. вище).
- **Capacitor / Cordova** — додає JS-bridge-залежності; для тонкого WebView надлишково (P6).

## Посилання

- [`mobile/README.md`](../../mobile/README.md) · [`mobile/app/src/main/java/ai/jarvis/mvp/MainActivity.java`](../../mobile/app/src/main/java/ai/jarvis/mvp/MainActivity.java)
- [`docs/CLIENTS_ROADMAP.md`](../CLIENTS_ROADMAP.md) § CL-3
